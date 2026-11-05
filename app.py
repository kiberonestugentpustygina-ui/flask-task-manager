from flask import Flask, render_template, request, jsonify, g
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
DB_NAME = os.environ.get("DB_NAME", "tasks.db")


# ---------- База данных ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                priority TEXT DEFAULT 'medium',
                category TEXT DEFAULT 'general',
                due_date TEXT DEFAULT '',
                done INTEGER DEFAULT 0,
                pinned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT DEFAULT NULL
            )
        """)
        # Миграция для старых баз (если колонки нет)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        if "pinned" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN pinned INTEGER DEFAULT 0")
        conn.commit()


def row_to_dict(row):
    return dict(row) if row else None


# ---------- Страница ----------
@app.route("/")
def index():
    return render_template("index.html")


# ---------- REST API ----------
@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    db = get_db()
    query = "SELECT * FROM tasks WHERE 1=1"
    params = []

    status = request.args.get("status")
    if status == "active":
        query += " AND done = 0"
    elif status == "done":
        query += " AND done = 1"

    priority = request.args.get("priority")
    if priority in ("low", "medium", "high"):
        query += " AND priority = ?"
        params.append(priority)

    category = request.args.get("category")
    if category:
        query += " AND category = ?"
        params.append(category)

    search = request.args.get("search")
    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    # Закреплённые всегда сверху, потом сортировка
    sort = request.args.get("sort", "created_desc")
    sort_map = {
        "created_desc": "created_at DESC",
        "created_asc": "created_at ASC",
        "priority": "CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END",
        "due_date": "CASE WHEN due_date = '' THEN 1 ELSE 0 END, due_date ASC",
    }
    query += f" ORDER BY pinned DESC, {sort_map.get(sort, 'created_at DESC')}"

    tasks = [row_to_dict(r) for r in db.execute(query, params).fetchall()]
    return jsonify(tasks)


@app.route("/api/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id):
    db = get_db()
    task = row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400

    priority = data.get("priority", "medium")
    if priority not in ("low", "medium", "high"):
        priority = "medium"

    db = get_db()
    cur = db.execute(
        """INSERT INTO tasks (title, description, priority, category, due_date)
           VALUES (?, ?, ?, ?, ?)""",
        (
            title,
            data.get("description", ""),
            priority,
            data.get("category", "general") or "general",
            data.get("due_date", ""),
        ),
    )
    db.commit()
    task = row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone())
    return jsonify(task), 201


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    data = request.get_json() or {}
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        return jsonify({"error": "Task not found"}), 404

    fields, params = [], []
    for field in ("title", "description", "priority", "category", "due_date", "pinned", "done"):
        if field in data:
            fields.append(f"{field} = ?")
            params.append(data[field])

    if fields:
        params.append(task_id)
        db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", params)
        db.commit()

    updated = row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    return jsonify(updated)


@app.route("/api/tasks/<int:task_id>/toggle", methods=["PATCH"])
def toggle_task(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        return jsonify({"error": "Task not found"}), 404

    new_done = 0 if task["done"] else 1
    completed_at = datetime.now().isoformat() if new_done else None
    db.execute(
        "UPDATE tasks SET done = ?, completed_at = ? WHERE id = ?",
        (new_done, completed_at, task_id),
    )
    db.commit()
    updated = row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    return jsonify(updated)


@app.route("/api/tasks/<int:task_id>/pin", methods=["PATCH"])
def pin_task(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        return jsonify({"error": "Task not found"}), 404
    new_pinned = 0 if task["pinned"] else 1
    db.execute("UPDATE tasks SET pinned = ? WHERE id = ?", (new_pinned, task_id))
    db.commit()
    updated = row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    return jsonify(updated)


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    db = get_db()
    task = row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    if not task:
        return jsonify({"error": "Task not found"}), 404
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    # Возвращаем задачу — пригодится для undo на клиенте
    return jsonify({"status": "deleted", "task": task})


@app.route("/api/tasks/restore", methods=["POST"])
def restore_task():
    """Восстановление удалённой задачи (undo)."""
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400

    db = get_db()
    cur = db.execute(
        """INSERT INTO tasks (title, description, priority, category, due_date, pinned, done)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            title,
            data.get("description", ""),
            data.get("priority", "medium"),
            data.get("category", "general"),
            data.get("due_date", ""),
            data.get("pinned", 0),
            data.get("done", 0),
        ),
    )
    db.commit()
    task = row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone())
    return jsonify(task), 201


@app.route("/api/tasks/clear-completed", methods=["DELETE"])
def clear_completed():
    db = get_db()
    cur = db.execute("DELETE FROM tasks WHERE done = 1")
    db.commit()
    return jsonify({"deleted": cur.rowcount})


# ---------- Категории ----------
@app.route("/api/categories", methods=["GET"])
def categories():
    db = get_db()
    rows = db.execute(
        "SELECT category, COUNT(*) as count FROM tasks GROUP BY category ORDER BY count DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ---------- Статистика ----------
@app.route("/api/stats", methods=["GET"])
def stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    done = db.execute("SELECT COUNT(*) FROM tasks WHERE done = 1").fetchone()[0]
    active = total - done
    pinned = db.execute("SELECT COUNT(*) FROM tasks WHERE pinned = 1").fetchone()[0]

    by_priority = {
        p: db.execute("SELECT COUNT(*) FROM tasks WHERE priority = ? AND done = 0", (p,)).fetchone()[0]
        for p in ("low", "medium", "high")
    }

    today = datetime.now().date().isoformat()
    overdue = db.execute(
        "SELECT COUNT(*) FROM tasks WHERE done = 0 AND due_date != '' AND due_date < ?",
        (today,),
    ).fetchone()[0]
    due_today = db.execute(
        "SELECT COUNT(*) FROM tasks WHERE done = 0 AND due_date = ?", (today,)
    ).fetchone()[0]

    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    done_week = db.execute(
        "SELECT COUNT(*) FROM tasks WHERE done = 1 AND completed_at >= ?", (week_ago,)
    ).fetchone()[0]

    return jsonify({
        "total": total,
        "active": active,
        "done": done,
        "overdue": overdue,
        "due_today": due_today,
        "pinned": pinned,
        "done_last_week": done_week,
        "by_priority": by_priority,
        "progress": round((done / total * 100) if total else 0, 1),
    })


# ---------- Экспорт ----------
@app.route("/api/export", methods=["GET"])
def export_tasks():
    db = get_db()
    tasks = [row_to_dict(r) for r in db.execute("SELECT * FROM tasks").fetchall()]
    return jsonify({
        "exported_at": datetime.now().isoformat(),
        "count": len(tasks),
        "tasks": tasks,
    })


# ---------- Точка входа ----------
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
