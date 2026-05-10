import json
import os
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

DATA_FILE = Path(__file__).parent / "tasks.json"

# In-memory cache: {id: {title, time, done, reminded}}
tasks_cache: dict[str, dict] = {}
reminded_set: set[str] = set()  # task ids already reminded today


def load_tasks():
    """Load today's tasks from JSON file."""
    global tasks_cache, reminded_set
    today = datetime.now().strftime("%Y-%m-%d")
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        day_data = data.get(today, {})
        tasks_cache = day_data.get("tasks", {})
        reminded_set = set(day_data.get("reminded", []))
    else:
        tasks_cache = {}
        reminded_set = set()


def save_tasks():
    """Save tasks to JSON file."""
    today = datetime.now().strftime("%Y-%m-%d")
    data = {}
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    # Keep only recent 7 days
    data = {k: v for k, v in data.items() if k >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")}
    data[today] = {"tasks": tasks_cache, "reminded": list(reminded_set)}
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def notify(title: str, message: str):
    """Show notification. Uses PowerShell on Windows, no-op on Linux (handled by frontend)."""
    if os.name != "nt":
        return  # Linux server: frontend handles notifications
    ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$template = @"
<toast>
  <visual>
    <binding template="ToastText02">
      <text id="1">{title}</text>
      <text id="2">{message}</text>
    </binding>
  </visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Task Reminder")
$notifier.Show($toast)
'''
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            timeout=10,
            capture_output=True,
        )
    except Exception:
        pass


def scheduler_loop():
    """Background thread: check tasks every second and trigger notifications."""
    while True:
        try:
            now = datetime.now()
            now_str = now.strftime("%H:%M")
            for task_id, task in list(tasks_cache.items()):
                if task.get("done"):
                    continue
                if task_id in reminded_set:
                    continue
                task_time = task.get("time", "")
                if task_time == now_str:
                    reminded_set.add(task_id)
                    save_tasks()
                    notify("事项提醒", task.get("title", "待办事项"))
        except Exception:
            pass
        time.sleep(1)


# --- Routes ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    today = datetime.now().strftime("%Y-%m-%d")
    items = []
    for task_id, task in tasks_cache.items():
        items.append({
            "id": task_id,
            "title": task.get("title", ""),
            "time": task.get("time", ""),
            "done": task.get("done", False),
            "reminded": task_id in reminded_set,
        })
    items.sort(key=lambda x: x["time"])
    return jsonify({"today": today, "tasks": items})


@app.route("/api/tasks", methods=["POST"])
def add_task():
    data = request.get_json()
    title = data.get("title", "").strip()
    task_time = data.get("time", "").strip()
    if not title or not task_time:
        return jsonify({"ok": False, "error": "事项和时间不能为空"}), 400
    task_id = str(uuid.uuid4())[:8]
    tasks_cache[task_id] = {"title": title, "time": task_time, "done": False}
    save_tasks()
    return jsonify({"ok": True, "id": task_id})


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    if task_id in tasks_cache:
        del tasks_cache[task_id]
        reminded_set.discard(task_id)
        save_tasks()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "not found"}), 404


@app.route("/api/tasks/<task_id>/done", methods=["PATCH"])
def toggle_done(task_id):
    if task_id in tasks_cache:
        tasks_cache[task_id]["done"] = not tasks_cache[task_id].get("done", False)
        save_tasks()
        return jsonify({"ok": True, "done": tasks_cache[task_id]["done"]})
    return jsonify({"ok": False, "error": "not found"}), 404


@app.route("/api/tasks/<task_id>/reset", methods=["PATCH"])
def reset_reminder(task_id):
    if task_id in tasks_cache:
        reminded_set.discard(task_id)
        save_tasks()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "not found"}), 404


if __name__ == "__main__":
    load_tasks()
    scheduler = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler.start()
    print("Task Reminder running at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
