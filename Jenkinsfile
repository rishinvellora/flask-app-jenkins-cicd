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
                        set -e

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

        stage('Prepare ASG') {
            steps {
                sh '''
                    set -e

                    echo "=========================================="
                    echo "Preparing Auto Scaling Group"
                    echo "=========================================="

                    echo "Suspending ASG ELB health replacement..."

                    aws autoscaling suspend-processes \
                        --auto-scaling-group-name "${ASG_NAME}" \
                        --scaling-processes HealthCheck ReplaceUnhealthy

                    echo "Setting ASG capacity to 2..."

                    aws autoscaling update-auto-scaling-group \
                        --auto-scaling-group-name "${ASG_NAME}" \
                        --min-size 2 \
                        --desired-capacity 2 \
                        --max-size 4

                    echo "Waiting for ASG instances..."

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
                        echo "ERROR: ASG did not provide two InService instances."
                        exit 1
                    fi

                    echo "Two ASG instances are ready."
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
                            echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
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


                            INSTANCE_IDS=$(aws autoscaling describe-auto-scaling-groups \
                                --auto-scaling-group-names "${ASG_NAME}" \
                                --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId' \
                                --output text)


                            if [ -z "${INSTANCE_IDS}" ] || [ "${INSTANCE_IDS}" = "None" ]; then
                                echo "ERROR: No ASG instances found."
                                exit 1
                            fi


                            echo "ASG instances:"
                            echo "${INSTANCE_IDS}"


                            for INSTANCE_ID in ${INSTANCE_IDS}; do

                                echo ""
                                echo "=========================================="
                                echo "Processing ${INSTANCE_ID}"
                                echo "=========================================="


                                PRIVATE_IP=$(aws ec2 describe-instances \
                                    --instance-ids "${INSTANCE_ID}" \
                                    --query 'Reservations[0].Instances[0].PrivateIpAddress' \
                                    --output text)


                                echo "Private IP: ${PRIVATE_IP}"


                                if [ -z "${PRIVATE_IP}" ] || [ "${PRIVATE_IP}" = "None" ]; then
                                    echo "ERROR: Could not find private IP."
                                    exit 1
                                fi


                                echo "Testing SSH..."

                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    -o ConnectTimeout=10 \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "echo SSH connection successful"


                                echo "Deregistering instance from ALB..."

                                aws elbv2 deregister-targets \
                                    --target-group-arn "${TARGET_GROUP_ARN}" \
                                    --targets Id="${INSTANCE_ID}"


                                sleep 10


                                echo "Saving previous image..."

                                PREVIOUS_IMAGE=$(ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "docker inspect taskboard --format '{{.Config.Image}}' 2>/dev/null || true")


                                if [ -z "${PREVIOUS_IMAGE}" ]; then
                                    PREVIOUS_IMAGE="${IMAGE_NAME}:latest"
                                fi


                                echo "Previous image: ${PREVIOUS_IMAGE}"


                                echo "Creating deployment environment..."

                                printf 'DATABASE_URL=%s\\n' "${DATABASE_URL}" |
                                    ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    'cat > /tmp/taskboard.env && chmod 600 /tmp/taskboard.env'


                                echo "Pulling build ${IMAGE_TAG}..."

                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "docker pull ${IMAGE_NAME}:${IMAGE_TAG}"


                                echo "Stopping old container..."

                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "docker stop taskboard || true; docker rm taskboard || true"


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


                                if [ "${HEALTHY}" != "true" ]; then

                                    echo "=========================================="
                                    echo "APPLICATION HEALTH CHECK FAILED"
                                    echo "Rolling back..."
                                    echo "=========================================="


                                    echo "New container logs:"

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


                                    echo "Checking rollback health..."

                                    ssh \
                                        -o StrictHostKeyChecking=no \
                                        ubuntu@"${PRIVATE_IP}" \
                                        "curl --fail --silent http://localhost:5000/health > /dev/null"


                                    echo "Registering rolled-back instance..."

                                    aws elbv2 register-targets \
                                        --target-group-arn "${TARGET_GROUP_ARN}" \
                                        --targets Id="${INSTANCE_ID}"


                                    exit 1
                                fi


                                echo "Application health check PASSED."


                                echo "Registering new version with ALB..."

                                aws elbv2 register-targets \
                                    --target-group-arn "${TARGET_GROUP_ARN}" \
                                    --targets Id="${INSTANCE_ID}"


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


                                if [ "${ALB_HEALTHY}" != "true" ]; then

                                    echo "=========================================="
                                    echo "ALB HEALTH CHECK FAILED"
                                    echo "Rolling back..."
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


                                    exit 1
                                fi


                                echo "ALB health check PASSED."


                                ssh \
                                    -o StrictHostKeyChecking=no \
                                    ubuntu@"${PRIVATE_IP}" \
                                    "rm -f /tmp/taskboard.env"


                                echo "Deployment successful on ${INSTANCE_ID}."

                            done


                            echo "=========================================="
                            echo "All ASG instances deployed successfully."
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

            echo "Resuming ASG health processes..."

            sh '''
                aws autoscaling resume-processes \
                    --auto-scaling-group-name "${ASG_NAME}" \
                    --scaling-processes HealthCheck ReplaceUnhealthy \
                    || true
            '''
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
            echo "Rollback was attempted where applicable."
            echo "=========================================="
        }
    }
}
