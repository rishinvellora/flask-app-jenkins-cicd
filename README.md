# TaskBoard — CI/CD DevOps Pipeline Project

A small Flask REST API used as a real-world vehicle to build a complete,
production-style CI/CD pipeline with Jenkins.

## What this project demonstrates
- REST API design (Flask + SQLite)
- Unit testing with coverage (pytest, pytest-cov)
- Static Application Security Testing / SAST (Bandit)
- Dependency vulnerability scanning (pip-audit)
- Container image vulnerability scanning (Trivy)
- Dockerized build & deployment
- Jenkins CI/CD pipeline as code (Jenkinsfile) using **Docker agents on a
  separate host** — not the master
- End-to-end tests against a live deployed instance
- Automated push to Docker Hub + remote deploy over SSH

## Architecture
```
GitHub push
   │
   ▼
Jenkins Master (VM1)
   │  (spins up ephemeral build container via Docker plugin)
   ▼
Docker Host (VM2) — build agent
   │
   ├── unit tests + coverage
   ├── bandit SAST
   ├── pip-audit dependency scan
   ├── docker build
   ├── trivy image scan
   ├── push image → Docker Hub
   └── SSH deploy → runs container on VM2, app live on port 5000
   │
   ▼
E2E tests hit the live container
   │
   ▼
Reports published in Jenkins (coverage, bandit, trivy) + archived artifacts
```

## API Endpoints
| Method | Endpoint         | Description         |
|--------|------------------|----------------------|
| GET    | /health          | Health check         |
| GET    | /tasks           | List all tasks       |
| POST   | /tasks           | Create a task        |
| GET    | /tasks/<id>      | Get a task           |
| PUT    | /tasks/<id>      | Update a task        |
| DELETE | /tasks/<id>      | Delete a task        |

## Run locally
```bash
pip install -r requirements.txt
python app.py
```

## Run tests
```bash
pip install -r requirements-dev.txt
pytest tests/test_app.py --cov=app
```

## Run with Docker
```bash
docker build -t taskflow-api .
docker run -p 5000:5000 taskflow-api
```

## CI/CD Pipeline
See [`Jenkinsfile`](./Jenkinsfile). Fully automated on every push to `main`:
test → scan → build → scan image → push → deploy → verify live (e2e).

## Stack
Python, Flask, SQLite, pytest, Bandit, pip-audit, Trivy, Docker, Jenkins,
Docker Hub.
