const form = document.getElementById("task-form");
const list = document.getElementById("task-list");
const dateDisplay = document.getElementById("date-display");

let lastReminded = {};
let notifyAllowed = false;

// Request browser notification permission (for mobile)
if ("Notification" in window && Notification.permission === "default") {
  Notification.requestPermission().then((p) => {
    notifyAllowed = p === "granted";
  });
} else if ("Notification" in window && Notification.permission === "granted") {
  notifyAllowed = true;
}

async function fetchTasks() {
  const res = await fetch("/api/tasks");
  const data = await res.json();
  dateDisplay.textContent = data.today;
  renderTasks(data.tasks);
}

function renderTasks(tasks) {
  if (tasks.length === 0) {
    list.innerHTML = '<div class="empty-state">还没有待办，添加第一个吧</div>';
    return;
  }

  list.innerHTML = tasks
    .map((t) => {
      const isReminding = t.reminded && !lastReminded[t.id];
      if (isReminding) {
        lastReminded[t.id] = true;
        // Browser notification (works on mobile)
        if (notifyAllowed) {
          new Notification("事项提醒", { body: t.title, icon: "/static/icon.svg" });
        }
        setTimeout(() => {
          lastReminded[t.id] = false;
          fetchTasks();
        }, 10000);
      }
      return `
        <li class="task-card${isReminding ? " reminding" : ""}${t.done ? " done" : ""}"
            id="task-${t.id}">
          <span class="task-time-badge">${t.time}</span>
          <span class="task-title">${esc(t.title)}</span>
          <span class="task-actions">
            <button class="btn-done" onclick="toggleDone('${t.id}')">
              ${t.done ? "还原" : "完成"}
            </button>
            <button class="btn-del" onclick="delTask('${t.id}')">删除</button>
          </span>
        </li>`;
    })
    .join("");
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const time = document.getElementById("task-time").value;
  const title = document.getElementById("task-title").value.trim();
  if (!time || !title) return;

  await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time, title }),
  });

  document.getElementById("task-time").value = "";
  document.getElementById("task-title").value = "";
  fetchTasks();
});

async function toggleDone(id) {
  await fetch(`/api/tasks/${id}/done`, { method: "PATCH" });
  fetchTasks();
}

async function delTask(id) {
  await fetch(`/api/tasks/${id}`, { method: "DELETE" });
  delete lastReminded[id];
  fetchTasks();
}

// Auto refresh every 10 seconds
fetchTasks();
setInterval(fetchTasks, 10000);
