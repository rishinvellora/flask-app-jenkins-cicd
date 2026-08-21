pipeline {
    agent {
        docker {
            image 'python:3.12-slim'
            args '-u root:root'
        }
    }

    environment {
        IMAGE_NAME   = "yourdockerhubuser/taskflow-api"
        IMAGE_TAG    = "${env.BUILD_NUMBER}"
        DEPLOY_HOST  = "deploy@<VM2_IP>"   // Docker host VM, SSH deploy target
        APP_PORT     = "5000"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                sh 'pip install --no-cache-dir -r requirements-dev.txt'
            }
        }

        stage('Unit Tests + Coverage') {
            steps {
                sh '''
                    pytest tests/test_app.py \
                        --cov=app --cov-report=xml --cov-report=html \
                        --junitxml=reports/unit-tests.xml
                '''
            }
            post {
                always {
                    junit 'reports/unit-tests.xml'
                    publishHTML(target: [
                        reportDir: 'htmlcov',
                        reportFiles: 'index.html',
                        reportName: 'Coverage Report'
                    ])
                }
            }
        }

        stage('Static Code Analysis (Bandit)') {
            steps {
                sh '''
                    bandit -r app.py -f html -o reports/bandit-report.html || true
                '''
            }
            post {
                always {
                    publishHTML(target: [
                        reportDir: 'reports',
                        reportFiles: 'bandit-report.html',
                        reportName: 'Bandit SAST Report'
                    ])
                }
            }
        }

        stage('Dependency Vulnerability Scan') {
            steps {
                sh '''
                    pip install pip-audit
                    pip-audit -r requirements.txt -f json -o reports/pip-audit.json || true
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'reports/pip-audit.json', allowEmptyArchive: true
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t ${IMAGE_NAME}:${IMAGE_TAG} -t ${IMAGE_NAME}:latest .'
            }
        }

        stage('Image Vulnerability Scan (Trivy)') {
            steps {
                sh '''
                    trivy image --severity HIGH,CRITICAL --format table \
                        --output reports/trivy-report.txt ${IMAGE_NAME}:${IMAGE_TAG} || true
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'reports/trivy-report.txt', allowEmptyArchive: true
                }
            }
        }

        stage('Push to Registry') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-creds',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh '''
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        docker push ${IMAGE_NAME}:${IMAGE_TAG}
                        docker push ${IMAGE_NAME}:latest
                    '''
                }
            }
        }

        stage('Deploy to VM2 (Docker Host)') {
            steps {
                sshagent(credentials: ['vm2-ssh-key']) {
                    sh '''
                        ssh -o StrictHostKeyChecking=no ${DEPLOY_HOST} "
                            docker pull ${IMAGE_NAME}:latest &&
                            docker stop taskflow-api || true &&
                            docker rm taskflow-api || true &&
                            docker run -d --name taskflow-api \
                                -p ${APP_PORT}:5000 \
                                -v taskflow-data:/data \
                                --restart unless-stopped \
                                ${IMAGE_NAME}:latest
                        "
                    '''
                }
            }
        }

        stage('E2E Tests Against Live Deployment') {
            steps {
                sh '''
                    sleep 5
                    BASE_URL=http://<VM2_IP>:${APP_PORT} pytest tests/test_e2e.py \
                        --junitxml=reports/e2e-tests.xml
                '''
            }
            post {
                always {
                    junit 'reports/e2e-tests.xml'
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
        }
        success {
            echo "Pipeline succeeded — TaskFlow API v${IMAGE_TAG} deployed and live."
        }
        failure {
            echo "Pipeline failed — check reports for details."
        }
    }
}
