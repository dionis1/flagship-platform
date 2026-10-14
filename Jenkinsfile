pipeline {
    agent any

    options {
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate Kubernetes YAML') {
            steps {
                sh '''
                    echo "Checking Kubernetes manifests..."

                    kubectl apply \
                      --dry-run=client \
                      -f kubernetes/dev/namespace.yaml

                    kubectl apply \
                      --dry-run=client \
                      -f kubernetes/dev/demo-app/
                '''
            }
        }

        stage('Basic Tests') {
            steps {
                sh '''
                    echo "Running basic repository checks..."

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
            echo 'Pipeline completed successfully.'
        }

        failure {
            echo 'Pipeline failed.'
        }
    }
}
