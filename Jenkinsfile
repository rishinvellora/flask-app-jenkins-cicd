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
                sh 'pip install -r requirements-dev.txt'
            }
        }

        stage('Unit Tests') {
            steps {
                sh 'pytest tests/test_app.py'
            }
        }
    }
}
