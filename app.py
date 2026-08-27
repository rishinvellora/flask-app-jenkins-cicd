"""
TaskBoard - A lightweight task management REST API.
Built for a CI/CD portfolio project: unit tests, SCA, vuln scanning,
E2E tests, Dockerized deployment.
"""

import os
import sqlite3
from datetime import datetime, timezone

import psycopg
from flask import Flask, g, jsonify, request
from psycopg.rows import dict_row

app = Flask(__name__)

DATABASE = os.environ.get("DATABASE_PATH", "taskboard.db")
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    db = getattr(g, "_database", None)

    if db is None:
        if DATABASE_URL:
            db = g._database = psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row,
            )
        else:
            db = g._database = sqlite3.connect(DATABASE)
            db.row_factory = sqlite3.Row

    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)

    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()

        if DATABASE_URL:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
        else:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

        db.commit()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/tasks", methods=["GET"])
def list_tasks():
    db = get_db()

    rows = db.execute(
        "SELECT * FROM tasks ORDER BY id"
    ).fetchall()

    return jsonify([dict(row) for row in rows]), 200


@app.route("/tasks", methods=["POST"])
def create_task():
    data = request.get_json(silent=True) or {}

    title = data.get("title", "").strip()

    if not title:
        return jsonify({"error": "title is required"}), 400

    db = get_db()

    created_at = datetime.now(timezone.utc).isoformat()

    if DATABASE_URL:
        cur = db.execute(
            """
            INSERT INTO tasks (title, done, created_at)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (title, 0, created_at),
        )

        new_task_id = cur.fetchone()["id"]

        db.commit()

        new_task = db.execute(
            "SELECT * FROM tasks WHERE id = %s",
            (new_task_id,),
        ).fetchone()

    else:
        cur = db.execute(
            """
            INSERT INTO tasks (title, done, created_at)
            VALUES (?, ?, ?)
            """,
            (title, 0, created_at),
        )

        new_task_id = cur.lastrowid

        db.commit()

        new_task = db.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (new_task_id,),
        ).fetchone()

    return jsonify(dict(new_task)), 201


@app.route("/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id):
    db = get_db()

    if DATABASE_URL:
        row = db.execute(
            "SELECT * FROM tasks WHERE id = %s",
            (task_id,),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    if row is None:
        return jsonify({"error": "task not found"}), 404

    return jsonify(dict(row)), 200


@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    db = get_db()

    if DATABASE_URL:
        row = db.execute(
            "SELECT * FROM tasks WHERE id = %s",
            (task_id,),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    if row is None:
        return jsonify({"error": "task not found"}), 404

    data = request.get_json(silent=True) or {}

    title = data.get("title", row["title"])
    done = int(bool(data.get("done", row["done"])))

    if DATABASE_URL:
        db.execute(
            """
            UPDATE tasks
            SET title = %s, done = %s
            WHERE id = %s
            """,
            (title, done, task_id),
        )

        updated = db.execute(
            "SELECT * FROM tasks WHERE id = %s",
            (task_id,),
        ).fetchone()

    else:
        db.execute(
            """
            UPDATE tasks
            SET title = ?, done = ?
            WHERE id = ?
            """,
            (title, done, task_id),
        )

        updated = db.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    db.commit()

    return jsonify(dict(updated)), 200


@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    db = get_db()

    if DATABASE_URL:
        row = db.execute(
            "SELECT * FROM tasks WHERE id = %s",
            (task_id,),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    if row is None:
        return jsonify({"error": "task not found"}), 404

    if DATABASE_URL:
        db.execute(
            "DELETE FROM tasks WHERE id = %s",
            (task_id,),
        )
    else:
        db.execute(
            "DELETE FROM tasks WHERE id = ?",
            (task_id,),
        )

    db.commit()

    return "", 204


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
