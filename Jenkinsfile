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
      resources:
        requests:
          cpu: "50m"
          memory: "64Mi"
        limits:
          cpu: "500m"
          memory: "256Mi"

    - name: buildkit
      image: moby/buildkit:v0.33.1
      command:
        - buildkitd
        - --addr
        - unix:///run/buildkit/buildkitd.sock
      securityContext:
        privileged: true
      tty: true
      resources:
        requests:
          cpu: "100m"
          memory: "128Mi"
        limits:
          cpu: "1000m"
          memory: "768Mi"
'''
            defaultContainer 'tools'
        }
    }

    options {
        skipDefaultCheckout(true)
    }

    environment {
        IMAGE_REPO = 'ghcr.io/dionis1/flagship-demo-app'
    }

    stages {

        stage('Install Tools') {
            steps {
                sh '''
                    echo "Installing CI tools..."

                    apk add --no-cache \
                      curl \
                      git \
                      ca-certificates

                    curl -LO \
                      "https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubectl"

                    install -m 0755 kubectl /usr/local/bin/kubectl
                    rm -f kubectl

                    echo "Installed versions:"
                    kubectl version --client
                    git --version
                '''
            }
        }

        stage('Checkout') {
            steps {
                checkout scm

                sh '''
                    git config --global --add safe.directory "$WORKSPACE"

                    echo "Repository checkout successful."
                    git rev-parse --show-toplevel
                    git status --short
                '''
            }
        }

        stage('Prepare') {
            steps {
                script {
                    def shortCommit = sh(
                        script: 'git rev-parse --short=7 HEAD',
                        returnStdout: true
                    ).trim()

                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${shortCommit}"
                }

                echo "Image to build:"
                echo "${IMAGE_REPO}:${IMAGE_TAG}"
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

                    test -f kubernetes/dev/namespace.yaml
                    test -f kubernetes/dev/demo-app/deployment.yaml
                    test -f kubernetes/dev/demo-app/service.yaml

                    test -f helm/datadog/values.yaml
                    test -f helm/jenkins/values.yaml

                    echo "All required files exist."
                    echo "Basic tests passed."
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
                        echo "Preparing GHCR authentication..."

                        mkdir -p "$WORKSPACE/.docker"

                        set +x

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

                        chmod 600 "$WORKSPACE/.docker/config.json"

                        set -x
                    '''

                    container('buildkit') {
                        sh '''
                            export DOCKER_CONFIG="$WORKSPACE/.docker"

                            BUILDKIT_ADDR="unix:///run/buildkit/buildkitd.sock"

                            echo "Waiting for BuildKit daemon..."

                            COUNT=0

                            until buildctl \
                              --addr "$BUILDKIT_ADDR" \
                              debug workers >/dev/null 2>&1
                            do
                                COUNT=$((COUNT + 1))

                                if [ "$COUNT" -ge 30 ]; then
                                    echo "BuildKit failed to become ready."
                                    exit 1
                                fi

                                sleep 1
                            done

                            echo "BuildKit is ready."

                            echo "Building:"
                            echo "${IMAGE_REPO}:${IMAGE_TAG}"

                            buildctl \
                              --addr "$BUILDKIT_ADDR" \
                              build \
                              --frontend dockerfile.v0 \
                              --local context=app \
                              --local dockerfile=app \
                              --output \
                              type=image,name=${IMAGE_REPO}:${IMAGE_TAG},push=true

                            echo "Container image pushed successfully."
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
                        echo "Updating GitOps manifest..."

                        git config --global --add safe.directory "$WORKSPACE"

                        sed -i \
                          "s#image: .*#image: ${IMAGE_REPO}:${IMAGE_TAG}#" \
                          kubernetes/dev/demo-app/deployment.yaml

                        echo "New image:"
                        grep "image:" \
                          kubernetes/dev/demo-app/deployment.yaml

                        git config user.name "Jenkins CI"
                        git config user.email "jenkins@localhost"

                        git add kubernetes/dev/demo-app/deployment.yaml

                        if git diff --cached --quiet
                        then
                            echo "No GitOps change required."
                            exit 0
                        fi

                        git commit \
                          -m "Deploy ${IMAGE_TAG} via Jenkins"

                        set +x

                        cat > /tmp/git-askpass.sh <<'EOF'
#!/bin/sh
case "$1" in
    *Username*)
        echo "$GIT_USER"
        ;;
    *Password*)
        echo "$GIT_TOKEN"
        ;;
esac
EOF

                        chmod 700 /tmp/git-askpass.sh

                        GIT_ASKPASS=/tmp/git-askpass.sh \
                        GIT_TERMINAL_PROMPT=0 \
                        git push \
                          https://github.com/dionis1/flagship-platform.git \
                          HEAD:main

                        rm -f /tmp/git-askpass.sh

                        set -x

                        echo "GitOps manifest pushed successfully."
                    '''
                }
            }
        }

        stage('Deployment Summary') {
            steps {
                echo "------------------------------------"
                echo "CI pipeline completed."
                echo "Image:"
                echo "${IMAGE_REPO}:${IMAGE_TAG}"
                echo ""
                echo "ArgoCD should now detect the Git change"
                echo "and synchronize the application."
                echo "------------------------------------"
            }
        }
    }

    post {

        success {
            echo "===================================="
            echo "CI PIPELINE SUCCESS"
            echo "===================================="
            echo "Published image:"
            echo "${IMAGE_REPO}:${IMAGE_TAG}"
            echo ""
            echo "ArgoCD should deploy the new version."
        }

        failure {
            echo "===================================="
            echo "CI PIPELINE FAILED"
            echo "===================================="
            echo "Check the failed stage above."
        }

        always {
            sh '''
                rm -rf "$WORKSPACE/.docker" || true
                rm -f /tmp/git-askpass.sh || true
            '''
        }
    }
}
