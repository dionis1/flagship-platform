pipeline {
    agent {
        kubernetes {
            yaml '''
apiVersion: v1
kind: Pod
spec:
  containers:
    - name: kubectl
      image: alpine:3.20
      command:
        - cat
      tty: true
      securityContext:
        runAsUser: 0
'''
            defaultContainer 'kubectl'
        }
    }

    stages {
        stage('Install kubectl') {
            steps {
                sh '''
                    apk add --no-cache curl
                    curl -LO "https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubectl"
                    install -m 0755 kubectl /usr/local/bin/kubectl
                    kubectl version --client
                '''
            }
        }

        stage('Validate Kubernetes YAML') {
            steps {
                sh '''
                    echo "Checking Kubernetes manifests..."

                    kubectl create \
  --dry-run=client \
  -f kubernetes/dev/namespace.yaml \
  -o yaml > /dev/null

kubectl create \
  --dry-run=client \
  -f kubernetes/dev/demo-app/ \
  -o yaml > /dev/null
                '''
            }
        }

        stage('Basic Tests') {
            steps {
                sh '''
                    test -f kubernetes/dev/demo-app/deployment.yaml
                    test -f kubernetes/dev/demo-app/service.yaml
                    test -f helm/datadog/values.yaml
                    test -f helm/jenkins/values.yaml

                    echo "All required files exist."
                '''
            }
        }
    }

    post {
        success {
            echo 'CI pipeline completed successfully.'
        }

        failure {
            echo 'CI pipeline failed.'
        }
    }
}
