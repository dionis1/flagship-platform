pipeline {
    agent {
        kubernetes {
            yaml '''
apiVersion: v1
kind: Pod
spec:
  containers:

    - name: tools
      image: alpine:3.20
      command:
        - cat
      tty: true
      securityContext:
        runAsUser: 0

    - name: buildkit
      image: moby/buildkit:rootless
      command:
        - sh
        - -c
        - sleep 99d
      tty: true
'''
            defaultContainer 'tools'
        }
    }

    environment {
        IMAGE_REPO = 'ghcr.io/dionis1/flagship-demo-app'
    }

    stages {

        stage('Install Tools') {
            steps {
                sh '''
                    apk add --no-cache \
                      curl \
                      git \
                      ca-certificates

                    curl -LO \
                      "https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubectl"

                    install -m 0755 kubectl /usr/local/bin/kubectl

                    kubectl version --client
                    git --version
                '''
            }
        }

        stage('Prepare') {
            steps {
                script {
                    env.IMAGE_TAG =
                        "${env.BUILD_NUMBER}-${env.GIT_COMMIT.take(7)}"
                }

                echo "Building ${IMAGE_REPO}:${IMAGE_TAG}"
            }
        }

        stage('Validate Kubernetes YAML') {
            steps {
                sh '''
                    echo "Validating Kubernetes manifests..."

                    kubectl create \
                      --dry-run=client \
                      -f kubernetes/dev/namespace.yaml \
                      -o yaml > /dev/null

                    kubectl create \
                      --dry-run=client \
                      -f kubernetes/dev/demo-app/ \
                      -o yaml > /dev/null

                    echo "Kubernetes manifests are valid."
                '''
            }
        }

        stage('Basic Tests') {
            steps {
                sh '''
                    echo "Running repository checks..."

                    test -f app/Dockerfile
                    test -f app/index.html

                    test -f kubernetes/dev/demo-app/deployment.yaml
                    test -f kubernetes/dev/demo-app/service.yaml

                    test -f helm/datadog/values.yaml
                    test -f helm/jenkins/values.yaml

                    echo "All tests passed."
                '''
            }
        }

        stage('Build & Push Image') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'ghcr-creds',
                        usernameVariable: 'GHCR_USER',
                        passwordVariable: 'GHCR_TOKEN'
                    )
                ]) {

                    sh '''
                        mkdir -p "$WORKSPACE/.docker"

                        AUTH=$(printf '%s:%s' \
                          "$GHCR_USER" "$GHCR_TOKEN" \
                          | base64 | tr -d '\\n')

                        cat > "$WORKSPACE/.docker/config.json" <<EOF
{
  "auths": {
    "ghcr.io": {
      "auth": "$AUTH"
    }
  }
}
EOF
                    '''

                    container('buildkit') {
                        sh '''
                            export DOCKER_CONFIG="$WORKSPACE/.docker"

                            buildctl-daemonless.sh build \
                              --frontend dockerfile.v0 \
                              --local context=app \
                              --local dockerfile=app \
                              --output \
                              type=image,name=${IMAGE_REPO}:${IMAGE_TAG},push=true
                        '''
                    }

                    sh '''
                        rm -rf "$WORKSPACE/.docker"
                    '''
                }
            }
        }

        stage('Update GitOps Manifest') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'github-push',
                        usernameVariable: 'GIT_USER',
                        passwordVariable: 'GIT_TOKEN'
                    )
                ]) {

                    sh '''
                        echo "Updating Kubernetes image..."

                        sed -i \
                          "s#image: .*#image: ${IMAGE_REPO}:${IMAGE_TAG}#" \
                          kubernetes/dev/demo-app/deployment.yaml

                        git config user.name "Jenkins CI"
                        git config user.email "jenkins@localhost"

                        git add kubernetes/dev/demo-app/deployment.yaml

                        git commit \
                          -m "Deploy ${IMAGE_TAG} via Jenkins"

                        cat > /tmp/git-askpass.sh <<'EOF'
#!/bin/sh
case "$1" in
    *Username*) echo "$GIT_USER" ;;
    *Password*) echo "$GIT_TOKEN" ;;
esac
EOF

                        chmod 700 /tmp/git-askpass.sh

                        GIT_ASKPASS=/tmp/git-askpass.sh \
                        GIT_TERMINAL_PROMPT=0 \
                        git push \
                          https://github.com/dionis1/flagship-platform.git \
                          HEAD:main

                        rm -f /tmp/git-askpass.sh
                    '''
                }
            }
        }
    }

    post {

        success {
            echo "CI successful."
            echo "Image: ${IMAGE_REPO}:${IMAGE_TAG}"
            echo "ArgoCD will deploy the new version."
        }

        failure {
            echo "CI pipeline failed."
        }

        always {
            sh '''
                rm -rf "$WORKSPACE/.docker" || true
            '''
        }
    }
}
