pipeline {
    agent any

    environment {
        IMAGE_NAME = "rishinraj/taskboard"
        IMAGE_TAG  = "${BUILD_NUMBER}"

        APP_A_HOST = "10.0.1.142"
        APP_B_HOST = "10.0.3.38"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    python3 -m venv .venv
                    .venv/bin/pip install --upgrade pip
                    .venv/bin/pip install -r requirements.txt
                    .venv/bin/pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Unit Tests + Coverage') {
            steps {
                sh '''
                    .venv/bin/pytest tests/test_app.py \
                        --cov=app \
                        --cov-report=term \
                        --cov-report=html
                '''
            }

            post {
                always {
                    publishHTML(target: [
                        reportDir: 'htmlcov',
                        reportFiles: 'index.html',
                        reportName: 'Coverage Report',
                        keepAll: true,
                        alwaysLinkToLastBuild: true
                    ])
                }
            }
        }

        stage('Code Quality') {
            steps {
                sh '.venv/bin/ruff check app.py tests/'
            }
        }

        stage('Dependency Vulnerability Scan') {
            steps {
                sh '.venv/bin/pip-audit -r requirements.txt'
            }
        }

        stage('Build Docker Image') {
            steps {
                sh '''
                    docker build \
                        -t taskboard:${BUILD_NUMBER} \
                        -t taskboard:latest \
                        .
                '''
            }
        }

        stage('Image Vulnerability Scan') {
            steps {
                sh '''
                    trivy image \
                        --cache-dir /var/cache/trivy \
                        --severity HIGH,CRITICAL \
                        --ignore-unfixed \
                        --exit-code 1 \
                        taskboard:${BUILD_NUMBER}
                '''
            }
        }

        stage('Push to Docker Hub') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'dockerhub-creds',
                        usernameVariable: 'DOCKER_USER',
                        passwordVariable: 'DOCKER_PASS'
                    )
                ]) {
                    sh '''
                        echo "$DOCKER_PASS" | docker login \
                            -u "$DOCKER_USER" \
                            --password-stdin

                        docker tag taskboard:${BUILD_NUMBER} \
                            ${IMAGE_NAME}:${BUILD_NUMBER}

                        docker tag taskboard:${BUILD_NUMBER} \
                            ${IMAGE_NAME}:latest

                        docker push ${IMAGE_NAME}:${BUILD_NUMBER}
                        docker push ${IMAGE_NAME}:latest

                        docker logout
                    '''
                }
            }
        }

        stage('Deploy to Application Servers') {
            steps {
                sshagent(credentials: ['taskboard-deploy-key']) {

                    sh '''
                        for HOST in "$APP_A_HOST" "$APP_B_HOST"; do

                            echo "=========================================="
                            echo "Deploying ${IMAGE_NAME}:${IMAGE_TAG}"
                            echo "Target: ${HOST}"
                            echo "=========================================="

                            ssh -o StrictHostKeyChecking=no \
                                ubuntu@${HOST} "
                                    docker pull ${IMAGE_NAME}:${IMAGE_TAG} &&
                                    docker stop taskboard || true &&
                                    docker rm taskboard || true &&
                                    docker run -d \
                                        --name taskboard \
                                        -p 5000:5000 \
                                        --restart unless-stopped \
                                        ${IMAGE_NAME}:${IMAGE_TAG}
                                "

                            echo "Waiting for TaskBoard to become healthy on ${HOST}..."

                            ssh -o StrictHostKeyChecking=no \
                                ubuntu@${HOST} '
                                    for i in {1..15}; do

                                        if curl \
                                            --fail \
                                            --silent \
                                            http://localhost:5000/health; then

                                            echo
                                            echo "TaskBoard is healthy."
                                            exit 0
                                        fi

                                        echo "Attempt $i/15: application not ready yet..."
                                        sleep 2
                                    done

                                    echo "TaskBoard failed health check."
                                    echo "Container logs:"
                                    docker logs taskboard

                                    exit 1
                                '

                            echo "Deployment successful on ${HOST}"
                        done
                    '''
                }
            }
        }
    }

    post {

        always {
            archiveArtifacts(
                artifacts: 'htmlcov/**',
                allowEmptyArchive: true
            )
        }

        success {
            echo "=========================================="
            echo "Pipeline succeeded."
            echo "TaskBoard ${IMAGE_NAME}:${IMAGE_TAG}"
            echo "deployed successfully to both application servers."
            echo "=========================================="
        }

        failure {
            echo "=========================================="
            echo "Pipeline failed."
            echo "Check the failed stage and Jenkins logs."
            echo "=========================================="
        }
    }
}
