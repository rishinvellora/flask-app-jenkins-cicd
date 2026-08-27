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

        RDS_HOST = "taskboard-db.c50e6q6g095i.ap-south-1.rds.amazonaws.com"
        RDS_PORT = "5432"
        RDS_DATABASE = "postgres"
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

                withCredentials([
                    usernamePassword(
                        credentialsId: 'taskboard-rds-db',
                        usernameVariable: 'DB_USER',
                        passwordVariable: 'DB_PASS'
                    )
                ]) {

                    sshagent(credentials: ['taskboard-deploy-key']) {

                        sh '''
                            set -e

                            echo "=========================================="
                            echo "Starting deployment: ${IMAGE_NAME}:${IMAGE_TAG}"
                            echo "=========================================="


                            DATABASE_URL=$(python3 -c '
import os
from urllib.parse import quote

user = quote(os.environ["DB_USER"], safe="")
password = quote(os.environ["DB_PASS"], safe="")
host = os.environ["RDS_HOST"]
port = os.environ["RDS_PORT"]
database = quote(os.environ["RDS_DATABASE"], safe="")

print(
    f"postgresql://{user}:{password}@{host}:{port}/{database}?sslmode=require"
)
')


                            deploy() {

                                HOST="$1"
                                INSTANCE_ID="$2"

                                echo "------------------------------------------"
                                echo "Deploying to ${HOST}"
                                echo "------------------------------------------"


                                PREVIOUS_IMAGE=$(ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${HOST}" \
                                    "docker inspect taskboard --format '{{.Config.Image}}'")


                                echo "Previous image: ${PREVIOUS_IMAGE}"


                                echo "Deregistering from ALB..."

                                aws elbv2 deregister-targets \
                                    --target-group-arn "${TARGET_GROUP_ARN}" \
                                    --targets Id="${INSTANCE_ID}"


                                sleep 10


                                echo "Creating database configuration..."

                                printf 'DATABASE_URL=%s\\n' "$DATABASE_URL" |
                                    ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${HOST}" \
                                    'cat > /tmp/taskboard.env && chmod 600 /tmp/taskboard.env'


                                echo "Pulling new image..."

                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${HOST}" \
                                    "docker pull ${IMAGE_NAME}:${IMAGE_TAG}"


                                echo "Stopping old container..."

                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${HOST}" \
                                    "docker stop taskboard || true; docker rm taskboard || true"


                                echo "Starting new container..."

                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${HOST}" \
                                    "
                                    docker run -d \
                                        --name taskboard \
                                        -p 5000:5000 \
                                        --restart unless-stopped \
                                        --env-file /tmp/taskboard.env \
                                        ${IMAGE_NAME}:${IMAGE_TAG}
                                    "


                                rm_env() {
                                    ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${HOST}" \
                                        "rm -f /tmp/taskboard.env"
                                }


                                echo "Checking application health..."

                                HEALTHY=false

                                for i in $(seq 1 15); do

                                    if ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${HOST}" \
                                        "curl --fail --silent http://localhost:5000/health > /dev/null"; then

                                        HEALTHY=true
                                        break
                                    fi

                                    echo "Waiting for application... ${i}/15"
                                    sleep 2
                                done


                                if [ "$HEALTHY" != "true" ]; then

                                    echo "New deployment failed."

                                    echo "Container logs:"
                                    ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${HOST}" \
                                        "docker logs taskboard || true"


                                    echo "Rolling back to ${PREVIOUS_IMAGE}..."

                                    ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${HOST}" \
                                        "
                                        docker stop taskboard || true
                                        docker rm taskboard || true

                                        docker pull ${PREVIOUS_IMAGE}

                                        docker run -d \
                                            --name taskboard \
                                            -p 5000:5000 \
                                            --restart unless-stopped \
                                            --env-file /tmp/taskboard.env \
                                            ${PREVIOUS_IMAGE}
                                        "


                                    sleep 5


                                    ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${HOST}" \
                                        "rm -f /tmp/taskboard.env"


                                    echo "Checking rollback health..."

                                    ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${HOST}" \
                                        "curl --fail --silent http://localhost:5000/health > /dev/null"


                                    echo "Registering rolled-back target..."

                                    aws elbv2 register-targets \
                                        --target-group-arn "${TARGET_GROUP_ARN}" \
                                        --targets Id="${INSTANCE_ID}"


                                    exit 1
                                fi


                                echo "Application health check passed."


                                rm_env


                                echo "Registering target with ALB..."

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

                                    echo "ALB state: ${STATE}"

                                    if [ "$STATE" = "healthy" ]; then
                                        echo "ALB health check passed."
                                        return 0
                                    fi

                                    sleep 5
                                done


                                echo "ALB health check failed."

                                return 1
                            }


                            deploy "${APP_A_HOST}" "${APP_A_ID}"

                            echo "App-A deployment successful."

                            deploy "${APP_B_HOST}" "${APP_B_ID}"

                            echo "App-B deployment successful."


                            echo "=========================================="
                            echo "Rolling deployment completed successfully."
                            echo "Version: ${IMAGE_NAME}:${IMAGE_TAG}"
                            echo "=========================================="
                        '''
                    }
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
            echo "Pipeline succeeded."
            echo "TaskBoard ${IMAGE_NAME}:${IMAGE_TAG} deployed successfully to both application servers."
        }

        failure {
            echo "Pipeline failed."
            echo "Check the deployment logs."
        }
    }
}
