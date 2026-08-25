pipeline {
    agent any

    environment {
        IMAGE_NAME = "rishinraj/taskboard"
        IMAGE_TAG  = "${BUILD_NUMBER}"

        APP_A_HOST = "10.0.1.142"
        APP_B_HOST = "10.0.3.38"

        APP_A_ID = "i-0db344a04b6533b27"
        APP_B_ID = "i-001b1fd77976b2a33"

        TARGET_GROUP_ARN = "arn:aws:elasticloadbalancing:ap-south-1:456687462288:targetgroup/taskboard-tg/30ba23715c142c08"
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
                sh '''
                    .venv/bin/ruff check app.py tests/
                '''
            }
        }

        stage('Dependency Vulnerability Scan') {
            steps {
                sh '''
                    .venv/bin/pip-audit -r requirements.txt
                '''
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
   
        /* 
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
        */

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

        stage('Rolling Deployment') {
            steps {
                sshagent(credentials: ['taskboard-deploy-key']) {

                    sh '''
                        set -e

                        deploy_server() {
                            HOST="$1"
                            INSTANCE_ID="$2"

                            echo "=========================================="
                            echo "Starting deployment"
                            echo "Host: ${HOST}"
                            echo "Instance: ${INSTANCE_ID}"
                            echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
                            echo "=========================================="

                            echo "Deregistering ${INSTANCE_ID} from ALB..."

                            aws elbv2 deregister-targets \
                                --target-group-arn "${TARGET_GROUP_ARN}" \
                                --targets Id="${INSTANCE_ID}"

                            echo "Waiting for existing connections to drain..."
                            sleep 10

                            echo "Deploying ${IMAGE_NAME}:${IMAGE_TAG}..."

                            ssh -o StrictHostKeyChecking=no \
                                ubuntu@"${HOST}" "
                                    docker pull ${IMAGE_NAME}:${IMAGE_TAG}

                                    docker stop taskboard || true
                                    docker rm taskboard || true

                                    docker run -d \
                                        --name taskboard \
                                        -p 5000:5000 \
                                        --restart unless-stopped \
                                        ${IMAGE_NAME}:${IMAGE_TAG}
                                "

                            echo "Waiting for application health..."

                            ssh -o StrictHostKeyChecking=no \
                                ubuntu@"${HOST}" '
                                    for i in $(seq 1 15); do

                                        if curl \
                                            --fail \
                                            --silent \
                                            http://localhost:5000/health; then

                                            echo
                                            echo "Application health check passed."
                                            exit 0
                                        fi

                                        echo "Attempt $i/15: application not ready yet..."
                                        sleep 2
                                    done

                                    echo "Application failed health check."

                                    echo "Container status:"
                                    docker ps -a

                                    echo "Container logs:"
                                    docker logs taskboard

                                    exit 1
                                '

                            echo "Registering ${INSTANCE_ID} with ALB..."

                            aws elbv2 register-targets \
                                --target-group-arn "${TARGET_GROUP_ARN}" \
                                --targets Id="${INSTANCE_ID}"

                            echo "Waiting for ALB health check..."

                            for i in $(seq 1 15); do

                                STATE=$(aws elbv2 describe-target-health \
                                    --target-group-arn "${TARGET_GROUP_ARN}" \
                                    --targets Id="${INSTANCE_ID}" \
                                    --query 'TargetHealthDescriptions[0].TargetHealth.State' \
                                    --output text)

                                echo "ALB target state: ${STATE}"

                                if [ "${STATE}" = "healthy" ]; then
                                    echo "ALB considers ${HOST} healthy."
                                    return 0
                                fi

                                sleep 5
                            done

                            echo "ALB health check failed for ${HOST}."

                            return 1
                        }

                        echo "=========================================="
                        echo "Rolling deployment started"
                        echo "Version: ${IMAGE_NAME}:${IMAGE_TAG}"
                        echo "=========================================="

                        deploy_server "${APP_A_HOST}" "${APP_A_ID}"

                        echo "App-A deployment successful."
                        echo "Proceeding to App-B..."

                        deploy_server "${APP_B_HOST}" "${APP_B_ID}"

                        echo "=========================================="
                        echo "Rolling deployment completed successfully."
                        echo "Version: ${IMAGE_NAME}:${IMAGE_TAG}"
                        echo "=========================================="
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
