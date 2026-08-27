pipeline {
    agent any

    environment {
        IMAGE_NAME = "rishinraj/taskboard"
        IMAGE_TAG  = "${BUILD_NUMBER}"

        ASG_NAME = "taskboard-asg"

        TARGET_GROUP_ARN = "arn:aws:elasticloadbalancing:ap-south-1:456687462288:targetgroup/taskboard-tg/30ba23715c142c08"

        RDS_HOST     = "taskboard-db.c50e6q6g095i.ap-south-1.rds.amazonaws.com"
        RDS_PORT     = "5432"
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
                        -t ${IMAGE_NAME}:${BUILD_NUMBER} \
                        .
                '''
            }
        }

        /*
        stage('Image Vulnerability Scan') {
            steps {
                sh '''
                    trivy image \
                        --severity HIGH,CRITICAL \
                        --ignore-unfixed \
                        --exit-code 1 \
                        ${IMAGE_NAME}:${BUILD_NUMBER}
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
                        set -e

                        echo "$DOCKER_PASS" | docker login \
                            -u "$DOCKER_USER" \
                            --password-stdin

                        docker push ${IMAGE_NAME}:${BUILD_NUMBER}

                        docker logout
                    '''
                }
            }
        }

        stage('Prepare ASG') {
            steps {
                sh '''
                    set -e

                    echo "=========================================="
                    echo "Preparing ASG"
                    echo "=========================================="

                    aws autoscaling update-auto-scaling-group \
                        --auto-scaling-group-name "${ASG_NAME}" \
                        --min-size 2 \
                        --desired-capacity 2 \
                        --max-size 4

                    echo "Waiting for two ASG instances..."

                    for i in $(seq 1 30); do

                        COUNT=$(aws autoscaling describe-auto-scaling-groups \
                            --auto-scaling-group-names "${ASG_NAME}" \
                            --query 'length(AutoScalingGroups[0].Instances[?LifecycleState==`InService`])' \
                            --output text)

                        echo "InService instances: ${COUNT}"

                        if [ "${COUNT}" -ge 2 ]; then
                            break
                        fi

                        sleep 10
                    done

                    COUNT=$(aws autoscaling describe-auto-scaling-groups \
                        --auto-scaling-group-names "${ASG_NAME}" \
                        --query 'length(AutoScalingGroups[0].Instances[?LifecycleState==`InService`])' \
                        --output text)

                    if [ "${COUNT}" -lt 2 ]; then
                        echo "ERROR: ASG did not reach 2 InService instances."
                        exit 1
                    fi
                '''
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
                            echo "Starting Rolling Deployment"
                            echo "Build: ${IMAGE_TAG}"
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


                            #
                            # Get ASG instances
                            #
                            INSTANCE_IDS=$(aws autoscaling describe-auto-scaling-groups \
                                --auto-scaling-group-names "${ASG_NAME}" \
                                --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId' \
                                --output text)


                            echo "ASG instances:"
                            echo "${INSTANCE_IDS}"


                            #
                            # Deploy one instance at a time
                            #
                            for INSTANCE_ID in ${INSTANCE_IDS}; do

                                echo ""
                                echo "=========================================="
                                echo "Deploying to ${INSTANCE_ID}"
                                echo "=========================================="


                                PRIVATE_IP=$(aws ec2 describe-instances \
                                    --instance-ids "${INSTANCE_ID}" \
                                    --query 'Reservations[0].Instances[0].PrivateIpAddress' \
                                    --output text)


                                echo "Private IP: ${PRIVATE_IP}"


                                #
                                # Wait for SSH
                                #
                                echo "Waiting for SSH..."

                                SSH_READY=false

                                for i in $(seq 1 30); do

                                    if ssh \
                                        -o StrictHostKeyChecking=no \
                                        -o ConnectTimeout=5 \
                                        ubuntu@"${PRIVATE_IP}" \
                                        "echo SSH connection successful"; then

                                        SSH_READY=true
                                        break
                                    fi

                                    echo "SSH not ready... ${i}/30"
                                    sleep 5

                                done


                                if [ "${SSH_READY}" != "true" ]; then
                                    echo "ERROR: SSH unavailable on ${PRIVATE_IP}"
                                    exit 1
                                fi


                                #
                                # Get previous image
                                #
                                PREVIOUS_IMAGE=$(ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "docker inspect taskboard --format '{{.Config.Image}}' 2>/dev/null || true")


                                if [ -z "${PREVIOUS_IMAGE}" ]; then
                                    PREVIOUS_IMAGE="${IMAGE_NAME}:latest"
                                fi


                                echo "Previous image: ${PREVIOUS_IMAGE}"


                                #
                                # Remove this instance from ALB
                                #
                                echo "Deregistering ${INSTANCE_ID}..."

                                aws elbv2 deregister-targets \
                                    --target-group-arn "${TARGET_GROUP_ARN}" \
                                    --targets Id="${INSTANCE_ID}"


                                sleep 10


                                #
                                # Transfer database configuration
                                #
                                printf 'DATABASE_URL=%s\\n' "${DATABASE_URL}" |
                                    ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    'cat > /tmp/taskboard.env && chmod 600 /tmp/taskboard.env'


                                #
                                # Pull new image
                                #
                                echo "Pulling ${IMAGE_NAME}:${IMAGE_TAG}..."

                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "docker pull ${IMAGE_NAME}:${IMAGE_TAG}"


                                #
                                # Stop old container
                                #
                                echo "Stopping old container..."

                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "docker stop taskboard || true; docker rm taskboard || true"


                                #
                                # Start new container
                                #
                                echo "Starting new container..."

                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "
                                    docker run -d \
                                        --name taskboard \
                                        -p 5000:5000 \
                                        --restart unless-stopped \
                                        --env-file /tmp/taskboard.env \
                                        ${IMAGE_NAME}:${IMAGE_TAG}
                                    "


                                #
                                # Application health check
                                #
                                echo "Checking application health..."

                                HEALTHY=false

                                for i in $(seq 1 20); do

                                    if ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${PRIVATE_IP}" \
                                        "curl --fail --silent http://localhost:5000/health > /dev/null"; then

                                        HEALTHY=true
                                        break
                                    fi

                                    echo "Waiting for application... ${i}/20"
                                    sleep 3

                                done


                                #
                                # APPLICATION FAILURE → ROLLBACK
                                #
                                if [ "${HEALTHY}" != "true" ]; then

                                    echo "=========================================="
                                    echo "APPLICATION HEALTH CHECK FAILED"
                                    echo "Rolling back ${INSTANCE_ID}"
                                    echo "=========================================="


                                    ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${PRIVATE_IP}" \
                                        "docker logs taskboard || true"


                                    ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${PRIVATE_IP}" \
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
                                        ubuntu@"${PRIVATE_IP}" \
                                        "curl --fail --silent http://localhost:5000/health > /dev/null"


                                    aws elbv2 register-targets \
                                        --target-group-arn "${TARGET_GROUP_ARN}" \
                                        --targets Id="${INSTANCE_ID}"


                                    echo "Rollback successful."

                                    exit 1
                                fi


                                echo "Application health check PASSED."


                                #
                                # Register new version
                                #
                                echo "Registering ${INSTANCE_ID} with ALB..."

                                aws elbv2 register-targets \
                                    --target-group-arn "${TARGET_GROUP_ARN}" \
                                    --targets Id="${INSTANCE_ID}"


                                #
                                # Wait for ALB health
                                #
                                echo "Waiting for ALB health..."

                                ALB_HEALTHY=false

                                for i in $(seq 1 20); do

                                    STATE=$(aws elbv2 describe-target-health \
                                        --target-group-arn "${TARGET_GROUP_ARN}" \
                                        --targets Id="${INSTANCE_ID}" \
                                        --query 'TargetHealthDescriptions[0].TargetHealth.State' \
                                        --output text)

                                    echo "ALB state: ${STATE}"

                                    if [ "${STATE}" = "healthy" ]; then

                                        ALB_HEALTHY=true
                                        break

                                    fi

                                    sleep 5

                                done


                                #
                                # ALB FAILURE → ROLLBACK
                                #
                                if [ "${ALB_HEALTHY}" != "true" ]; then

                                    echo "=========================================="
                                    echo "ALB HEALTH CHECK FAILED"
                                    echo "Rolling back ${INSTANCE_ID}"
                                    echo "=========================================="


                                    aws elbv2 deregister-targets \
                                        --target-group-arn "${TARGET_GROUP_ARN}" \
                                        --targets Id="${INSTANCE_ID}"


                                    ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${PRIVATE_IP}" \
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
                                        ubuntu@"${PRIVATE_IP}" \
                                        "curl --fail --silent http://localhost:5000/health > /dev/null"


                                    aws elbv2 register-targets \
                                        --target-group-arn "${TARGET_GROUP_ARN}" \
                                        --targets Id="${INSTANCE_ID}"


                                    echo "Rollback successful."

                                    exit 1
                                fi


                                echo "ALB health check PASSED."


                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "rm -f /tmp/taskboard.env"


                                echo "Deployment successful on ${INSTANCE_ID}."

                            done


                            echo ""
                            echo "=========================================="
                            echo "ROLLING DEPLOYMENT COMPLETED"
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
            echo "=========================================="
            echo "Pipeline succeeded."
            echo "TaskBoard ${IMAGE_NAME}:${IMAGE_TAG}"
            echo "deployed successfully to the ASG."
            echo "=========================================="
        }

        failure {
            echo "=========================================="
            echo "Pipeline failed."
            echo "Check the deployment logs."
            echo "=========================================="
        }
    }
}
