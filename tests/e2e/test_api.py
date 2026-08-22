import requests

BASE_URL = "http://localhost:5000"


def test_health_e2e():
    response = requests.get(f"{BASE_URL}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_task_e2e():
    # Create a task
    create_response = requests.post(
        f"{BASE_URL}/tasks",
        json={"title": "E2E Task"},
    )

    assert create_response.status_code == 201

    created_task = create_response.json()
    task_id = created_task["id"]

    assert created_task["title"] == "E2E Task"
    assert created_task["done"] == 0

    # Retrieve the task
    get_response = requests.get(
        f"{BASE_URL}/tasks/{task_id}"
    )

    assert get_response.status_code == 200

    task = get_response.json()

    assert task["id"] == task_id
    assert task["title"] == "E2E Task"
