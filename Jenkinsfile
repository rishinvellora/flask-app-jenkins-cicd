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

        stage('Rolling Deployment with Rollback') {

            steps {

                sshagent(credentials: ['taskboard-deploy-key']) {

                    sh '''
                        set -e

                        deploy_container() {
                            HOST="$1"
                            IMAGE="$2"

                            echo "Deploying ${IMAGE} to ${HOST}"

                            ssh -o StrictHostKeyChecking=no \
                                ubuntu@"${HOST}" "
                                    docker pull ${IMAGE}

                                    docker stop taskboard || true
                                    docker rm taskboard || true

                                    docker run -d \
                                        --name taskboard \
                                        -p 5000:5000 \
                                        --restart unless-stopped \
                                        ${IMAGE}
                                "
                        }


                        check_application_health() {
                            HOST="$1"

                            echo "Checking application health on ${HOST}..."

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

                                        echo "Attempt $i/15: application not ready..."
                                        sleep 2
                                    done

                                    echo "Application health check failed."

                                    docker ps -a

                                    echo "Container logs:"
                                    docker logs taskboard

                                    exit 1
                                '
                        }


                        deregister_target() {
                            INSTANCE_ID="$1"

                            echo "Deregistering ${INSTANCE_ID} from ALB..."

                            aws elbv2 deregister-targets \
                                --target-group-arn "${TARGET_GROUP_ARN}" \
                                --targets Id="${INSTANCE_ID}"

                            echo "Waiting for connections to drain..."

                            sleep 10
                        }


                        register_target() {
                            INSTANCE_ID="$1"

                            echo "Registering ${INSTANCE_ID} with ALB..."

                            aws elbv2 register-targets \
                                --target-group-arn "${TARGET_GROUP_ARN}" \
                                --targets Id="${INSTANCE_ID}"

                            echo "Waiting for ALB health..."

                            for i in $(seq 1 15); do

                                STATE=$(aws elbv2 describe-target-health \
                                    --target-group-arn "${TARGET_GROUP_ARN}" \
                                    --targets Id="${INSTANCE_ID}" \
                                    --query 'TargetHealthDescriptions[0].TargetHealth.State' \
                                    --output text)

                                echo "ALB target state: ${STATE}"

                                if [ "${STATE}" = "healthy" ]; then
                                    echo "ALB considers target healthy."
                                    return 0
                                fi

                                sleep 5
                            done

                            echo "ALB health check failed."

                            return 1
                        }


                        get_previous_image() {
                            HOST="$1"

                            ssh -o StrictHostKeyChecking=no \
                                ubuntu@"${HOST}" \
                                "docker inspect taskboard --format '{{.Config.Image}}'"
                        }


                        rollback_server() {
                            HOST="$1"
                            INSTANCE_ID="$2"
                            PREVIOUS_IMAGE="$3"

                            echo "=========================================="
                            echo "ROLLBACK"
                            echo "Host: ${HOST}"
                            echo "Previous image: ${PREVIOUS_IMAGE}"
                            echo "=========================================="

                            echo "Ensuring target is deregistered..."

                            aws elbv2 deregister-targets \
                                --target-group-arn "${TARGET_GROUP_ARN}" \
                                --targets Id="${INSTANCE_ID}" || true

                            sleep 5

                            echo "Restoring ${PREVIOUS_IMAGE}..."

                            ssh -o StrictHostKeyChecking=no \
                                ubuntu@"${HOST}" "
                                    docker pull ${PREVIOUS_IMAGE}

                                    docker stop taskboard || true
                                    docker rm taskboard || true

                                    docker run -d \
                                        --name taskboard \
                                        -p 5000:5000 \
                                        --restart unless-stopped \
                                        ${PREVIOUS_IMAGE}
                                "

                            echo "Checking rollback application health..."

                            check_application_health "${HOST}"

                            echo "Registering restored target..."

                            register_target "${INSTANCE_ID}"

                            echo "Rollback completed successfully."
                        }


                        echo "=========================================="
                        echo "Starting rolling deployment"
                        echo "New image: ${IMAGE_NAME}:${IMAGE_TAG}"
                        echo "=========================================="


                        echo "Getting current image from App-A..."

                        PREVIOUS_APP_A=$(get_previous_image "${APP_A_HOST}")

                        echo "App-A current image: ${PREVIOUS_APP_A}"


                        echo "Getting current image from App-B..."

                        PREVIOUS_APP_B=$(get_previous_image "${APP_B_HOST}")

                        echo "App-B current image: ${PREVIOUS_APP_B}"


                        echo "=========================================="
                        echo "Deploying App-A"
                        echo "=========================================="


                        deregister_target "${APP_A_ID}"


                        if ! deploy_container \
                            "${APP_A_HOST}" \
                            "${IMAGE_NAME}:${IMAGE_TAG}"; then

                            echo "App-A deployment command failed."

                            rollback_server \
                                "${APP_A_HOST}" \
                                "${APP_A_ID}" \
                                "${PREVIOUS_APP_A}"

                            exit 1
                        fi


                        if ! check_application_health "${APP_A_HOST}"; then

                            echo "App-A health check failed."

                            rollback_server \
                                "${APP_A_HOST}" \
                                "${APP_A_ID}" \
                                "${PREVIOUS_APP_A}"

                            exit 1
                        fi


                        if ! register_target "${APP_A_ID}"; then

                            echo "App-A ALB health check failed."

                            rollback_server \
                                "${APP_A_HOST}" \
                                "${APP_A_ID}" \
                                "${PREVIOUS_APP_A}"

                            exit 1
                        fi


                        echo "App-A successfully deployed."


                        echo "=========================================="
                        echo "Deploying App-B"
                        echo "=========================================="


                        deregister_target "${APP_B_ID}"


                        if ! deploy_container \
                            "${APP_B_HOST}" \
                            "${IMAGE_NAME}:${IMAGE_TAG}"; then

                            echo "App-B deployment command failed."

                            echo "Rolling back App-A..."

                            rollback_server \
                                "${APP_A_HOST}" \
                                "${APP_A_ID}" \
                                "${PREVIOUS_APP_A}"

                            echo "Rolling back App-B..."

                            rollback_server \
                                "${APP_B_HOST}" \
                                "${APP_B_ID}" \
                                "${PREVIOUS_APP_B}"

                            exit 1
                        fi


                        if ! check_application_health "${APP_B_HOST}"; then

                            echo "App-B health check failed."

                            echo "Rolling back App-A..."

                            rollback_server \
                                "${APP_A_HOST}" \
                                "${APP_A_ID}" \
                                "${PREVIOUS_APP_A}"

                            echo "Rolling back App-B..."

                            rollback_server \
                                "${APP_B_HOST}" \
                                "${APP_B_ID}" \
                                "${PREVIOUS_APP_B}"

                            exit 1
                        fi


                        if ! register_target "${APP_B_ID}"; then

                            echo "App-B ALB health check failed."

                            echo "Rolling back App-A..."

                            rollback_server \
                                "${APP_A_HOST}" \
                                "${APP_A_ID}" \
                                "${PREVIOUS_APP_A}"

                            echo "Rolling back App-B..."

                            rollback_server \
                                "${APP_B_HOST}" \
                                "${APP_B_ID}" \
                                "${PREVIOUS_APP_B}"

                            exit 1
                        fi


                        echo "App-B successfully deployed."


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
            echo "If deployment failed, rollback was attempted."
            echo "Check the deployment logs for details."
            echo "=========================================="
        }
    }
}
