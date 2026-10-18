pipeline {
    agent none
    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 25, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '15', artifactNumToKeepStr: '10'))
    }
    environment {
        IMAGE_REPO = 'ghcr.io/dionis1/flagship-demo-app'
        KUBERNETES_VERSION = '1.31.0'
        PIPELINE_ACTION = 'skip'
    }
    stages {
        stage('Classify trusted main changes') {
            agent {
                kubernetes {
                    defaultContainer 'tools'
                    yaml '''
apiVersion: v1
kind: Pod
spec:
  automountServiceAccountToken: false
  containers:
    - name: tools
      image: alpine:3.20
      command: [cat]
      tty: true
      resources:
        requests: {cpu: 50m, memory: 64Mi}
        limits: {cpu: 500m, memory: 256Mi}
'''
                }
            }
            steps {
                script {
                    // The job must load this Jenkinsfile only from trusted main.
                    // Never configure this credentialed job to run fork/PR Jenkinsfiles.
                    if (env.CHANGE_ID || (env.BRANCH_NAME && env.BRANCH_NAME != 'main')) {
                        error('This delivery job accepts trusted main builds only')
                    }
                }
                checkout scm
                sh 'apk add --no-cache git python3; mkdir -p reports; git config --global --add safe.directory "$WORKSPACE"'
                script {
                    def branch = env.BRANCH_NAME ?: env.GIT_BRANCH
                    if (!(branch in ['main', 'origin/main', 'refs/remotes/origin/main'])) {
                        error('Configure SCM branch main; missing or unexpected branch identity')
                    }
                    env.SOURCE_REVISION = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${env.SOURCE_REVISION.take(7)}"
                    env.PIPELINE_ACTION = sh(
                        script: 'python3 ci/change_policy.py "${GIT_PREVIOUS_SUCCESSFUL_COMMIT:-}"',
                        returnStdout: true
                    ).trim()
                    currentBuild.description = "${env.PIPELINE_ACTION}: ${env.SOURCE_REVISION.take(7)}"
                }
                sh 'python3 -m unittest discover -s tests -v'
                stash name: 'source', includes: '**/*,.git/**', useDefaultExcludes: false,
                      excludes: 'reports/**,.docker/**,__pycache__/**,**/__pycache__/**'
                echo "Change policy: ${env.PIPELINE_ACTION}; no privileged pod or deployment credentials used yet"
            }
        }
        stage('Validate infrastructure-only changes') {
            when {
                beforeAgent true
                expression { env.PIPELINE_ACTION == 'validate' }
            }
            agent {
                kubernetes {
                    defaultContainer 'tools'
                    yaml '''
apiVersion: v1
kind: Pod
spec:
  automountServiceAccountToken: false
  containers:
    - name: tools
      image: alpine:3.20
      command: [cat]
      tty: true
      resources:
        requests: {cpu: 50m, memory: 128Mi}
        limits: {cpu: 1000m, memory: 512Mi}
'''
                }
            }
            steps {
                unstash 'source'
                sh 'git config --global --add safe.directory "$WORKSPACE"; sh ci/install-tools.sh; sh ci/validate.sh'
            }
            post {
                always { archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true }
            }
        }
        stage('Validate and deliver') {
            when {
                beforeAgent true
                expression { env.PIPELINE_ACTION == 'build' }
            }
            agent {
                kubernetes {
                    defaultContainer 'tools'
                    yaml '''
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: flagship-ci
  containers:
    - name: tools
      image: alpine:3.20
      command: [cat]
      tty: true
      resources:
        requests: {cpu: 50m, memory: 128Mi}
        limits: {cpu: 1000m, memory: 768Mi}
    - name: buildkit
      image: moby/buildkit:v0.33.1
      command: [buildkitd, --addr, unix:///run/buildkit/buildkitd.sock]
      securityContext: {privileged: true}
      resources:
        requests: {cpu: 100m, memory: 128Mi}
        limits: {cpu: 1000m, memory: 768Mi}
'''
                }
            }
            stages {
                stage('Tools and manifest validation') {
                    steps {
                        unstash 'source'
                        sh 'git config --global --add safe.directory "$WORKSPACE"; sh ci/install-tools.sh; sh ci/validate.sh'
                    }
                }
                stage('Build candidate image') {
                    when { expression { env.PIPELINE_ACTION == 'build' } }
                    steps {
                        withCredentials([usernamePassword(credentialsId: 'ghcr-creds',
                            usernameVariable: 'GHCR_USER', passwordVariable: 'GHCR_TOKEN')]) {
                            sh '''
                                set +x
                                umask 077
                                mkdir -p "$WORKSPACE/.docker"
                                python3 - <<'PY'
import base64, json, os
from pathlib import Path
value = base64.b64encode((os.environ['GHCR_USER'] + ':' + os.environ['GHCR_TOKEN']).encode()).decode()
Path('.docker/config.json').write_text(json.dumps({'auths': {'ghcr.io': {'auth': value}}}))
PY
                            '''
                            container('buildkit') {
                                sh '''
                                    set -eu
                                    export DOCKER_CONFIG="$WORKSPACE/.docker"
                                    n=0
                                    until buildctl debug workers >/dev/null 2>&1; do
                                        n=$((n+1)); test "$n" -lt 30; sleep 1
                                    done
                                    buildctl build --frontend dockerfile.v0 \
                                        --local context=app --local dockerfile=app \
                                        --metadata-file reports/build.json \
                                        --output "type=image,name=${IMAGE_REPO}:${IMAGE_TAG},push=true"
                                '''
                            }
                        }
                        script {
                            env.CANDIDATE_IMAGE = sh(script: '''python3 - <<'PY'
import json, os, re
meta = json.load(open('reports/build.json'))
digest = meta['containerimage.digest']
assert re.fullmatch(r'sha256:[0-9a-f]{64}', digest)
print(os.environ['IMAGE_REPO'] + '@' + digest)
PY''', returnStdout: true).trim()
                        }
                    }
                }
                stage('Scan candidate image') {
                    when { expression { env.PIPELINE_ACTION == 'build' } }
                    steps {
                        withCredentials([usernamePassword(credentialsId: 'ghcr-creds',
                            usernameVariable: 'TRIVY_USERNAME', passwordVariable: 'TRIVY_PASSWORD')]) {
                            sh '''
                                set +x
                                trivy image --scanners vuln --severity HIGH,CRITICAL \
                                    --exit-code 1 --timeout 5m --format json \
                                    --output reports/trivy.json "$CANDIDATE_IMAGE"
                            '''
                        }
                    }
                }
                stage('HTTP test built image') {
                    when { expression { env.PIPELINE_ACTION == 'build' } }
                    steps {
                        timeout(time: 3, unit: 'MINUTES') {
                            sh 'python3 ci/kube_checks.py image --image "$CANDIDATE_IMAGE"'
                        }
                    }
                }
                stage('Promote tested digest in Git') {
                    when { expression { env.PIPELINE_ACTION == 'build' } }
                    steps {
                        withCredentials([usernamePassword(credentialsId: 'github-push',
                            usernameVariable: 'GIT_USER', passwordVariable: 'GIT_TOKEN')]) {
                            sh '''
                                set +x
                                export GIT_ASKPASS="$WORKSPACE/ci/git-askpass.sh" GIT_TERMINAL_PROMPT=0
                                python3 ci/promote.py --source "$SOURCE_REVISION" --image "$CANDIDATE_IMAGE"
                            '''
                        }
                    }
                }
                stage('Verify GitOps deployment') {
                    when { expression { env.PIPELINE_ACTION == 'build' } }
                    steps {
                        timeout(time: 8, unit: 'MINUTES') {
                            sh '''
                                python3 ci/kube_checks.py deployment --image "$CANDIDATE_IMAGE" \
                                    --revision "$(cat reports/deployment-revision.txt)" --timeout 360
                            '''
                        }
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
                    sh 'rm -rf "$WORKSPACE/.docker"'
                }
            }
        }
    }
    post {
        success {
            echo "Completed ${env.PIPELINE_ACTION}. A build is successful only after image gates and revision-aware deployment verification."
        }
        failure {
            echo 'Failed: inspect the stage and archived reports. A pushed candidate is not a verified deployment.'
        }
    }
}
