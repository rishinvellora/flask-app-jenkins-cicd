import pytest

import app as app_module
from app import app, init_db


@pytest.fixture
def client(tmp_path):
    test_db = tmp_path / "test.db"

    # Point the application at the temporary test database
    app_module.DATABASE = str(test_db)

    app.config["TESTING"] = True

    # Create the database schema in the temporary database
    init_db()

    with app.test_client() as client:
        yield client



def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}



def test_create_task(client):
    response = client.post(
        "/tasks",
        json={"title": "Learn CI/CD"},
    )

    assert response.status_code == 201

    data = response.get_json()

    assert data["title"] == "Learn CI/CD"
    assert data["done"] == 0
    assert "id" in data
    assert "created_at" in data



def test_list_tasks(client):
    client.post(
        "/tasks",
        json={"title": "Task One"},
    )
    client.post(
        "/tasks",
        json={"title": "Task Two"},
    )

    response = client.get("/tasks")

    assert response.status_code == 200

    data = response.get_json()

    assert len(data) == 2
    assert data[0]["title"] == "Task One"
    assert data[1]["title"] == "Task Two"



def test_get_task(client):
    create_response = client.post(
        "/tasks",
        json={"title": "Find Me"},
    )

    task_id = create_response.get_json()["id"]

    response = client.get(f"/tasks/{task_id}")

    assert response.status_code == 200

    data = response.get_json()

    assert data["id"] == task_id
    assert data["title"] == "Find Me"



def test_update_task(client):
    create_response = client.post(
        "/tasks",
        json={"title": "Old Title"},
    )

    task_id = create_response.get_json()["id"]

    response = client.put(
        f"/tasks/{task_id}",
        json={
            "title": "New Title",
            "done": True,
        },
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["id"] == task_id
    assert data["title"] == "New Title"
    assert data["done"] == 1



def test_delete_task(client):
    create_response = client.post(
        "/tasks",
        json={"title": "Delete Me"},
    )

    task_id = create_response.get_json()["id"]

    response = client.delete(f"/tasks/{task_id}")

    assert response.status_code == 204

    get_response = client.get(f"/tasks/{task_id}")

    assert get_response.status_code == 404



def test_create_task_without_title(client):
    response = client.post(
        "/tasks",
        json={},
    )

    assert response.status_code == 400

    data = response.get_json()

    assert data["error"] == "title is required"



def test_get_nonexistent_task(client):
    response = client.get("/tasks/9999")

    assert response.status_code == 404

    data = response.get_json()

    assert data["error"] == "task not found"



def test_update_nonexistent_task(client):
    response = client.put(
        "/tasks/9999",
        json={
            "title": "Doesn't exist",
            "done": True,
        },
    )

    assert response.status_code == 404

    data = response.get_json()

    assert data["error"] == "task not found"



def test_delete_nonexistent_task(client):
    response = client.delete("/tasks/9999")

    assert response.status_code == 404

    data = response.get_json()

    assert data["error"] == "task not found"
