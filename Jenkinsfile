pipeline {
    agent any

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

        stage('Dependency vulnerability scan') {
	    steps {
	        sh '.venv/bin/pip-audit -r requirements.txt'
	    }
	}		    
        
        stage('Build docker image') {
	    steps {
	        sh '''
		    docker build -t taskboard:${BUILD_NUMBER} .
		    docker tag taskboard:${BUILD_NUMBER} taskboard:latest
		'''
	    }
	}

	stage('Docker image vulnerability scan') {
	    steps { 
		sh '''
		    trivy image --severity HIGH,CRITICAL \
                    --cache-dir /var/cache/trivy \
		    --exit-code 1 \
		    taskboard:${BUILD_NUMBER}
		'''
	    }
	}
    }
}
