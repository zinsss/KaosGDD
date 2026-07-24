const routes = {
  today: "Today",
  calendar: "Calendar",
  tasks: "Tasks",
  services: "Services",
};

const state = {
  selectedDate: "2026-07-24",
  taskMode: "now",
  taskDescriptions: {},
};

const mockCalendarData = {
  events: [
    { uid: "vaccine-prep", summary: "Vaccine room prep", dtstart: "2026-07-24T09:00:00", source: "Clinic" },
    { uid: "supplies-review", summary: "Supplies review", dtstart: "2026-07-24T11:30:00", source: "KaosSupplies" },
    { uid: "roun-check", summary: "ROUN timetable check", dtstart: "2026-07-24T17:00:00", source: "Family" },
    { uid: "scan-review", summary: "Scan queue review", dtstart: "2026-07-27T10:00:00", source: "PACS" },
    { uid: "paperless-cleanup", summary: "Paperless archive pass", dtstart: "2026-07-30T15:00:00", source: "Documents" },
  ],
  tasks: [
    {
      uid: "fax-result",
      summary: "Review incoming fax result",
      description: "Fax follow-up notes\n\n-- confirm sender\n-- attach PDF\n-x send fax notification",
      due: "2026-07-24",
      status: "NEEDS-ACTION",
      categories: ["fax", "now", "urgent"],
      source: "Radicale mock",
    },
    {
      uid: "scan-queue",
      summary: "Check scan queue",
      description: "PACS check\n\n-- review failed imports\n-- confirm scan queue",
      due: "2026-07-24",
      status: "NEEDS-ACTION",
      categories: ["pacs", "now"],
      source: "Radicale mock",
    },
    {
      uid: "supply-sync",
      summary: "Daily supply sync",
      description: "Daily repeat\n\n-- compare low-stock list\n-- update order note",
      due: "2026-07-24",
      status: "NEEDS-ACTION",
      categories: ["supplies", "today", "repeat"],
      source: "Radicale mock",
    },
    {
      uid: "roun-window",
      summary: "Confirm ROUN timetable window",
      description: "Standalone family module\n\n-- check school pickup window",
      due: "2026-07-24",
      status: "NEEDS-ACTION",
      categories: ["family", "today"],
      source: "Radicale mock",
    },
    {
      uid: "paperless-inbox",
      summary: "Paperless inbox check",
      description: "Inbox cleared at 08:40\n\n-x archive complete",
      due: "2026-07-24",
      status: "COMPLETED",
      completed: "2026-07-24T08:40:00",
      categories: ["documents"],
      source: "Radicale mock",
    },
    {
      uid: "wiki-note",
      summary: "Move protocol notes to Wiki.js",
      description: "Knowledge cleanup\n\n-- move vaccine protocol\n-- link from KaosGDD",
      due: "2026-07-30",
      status: "NEEDS-ACTION",
      categories: ["knowledge", "later"],
      source: "Radicale mock",
    },
  ],
};

const mockAdapter = {
  getEvents() {
    return mockCalendarData.events.map(normalizeEvent);
  },

  getTasks() {
    return mockCalendarData.tasks.map(normalizeTask);
  },

  getServices() {
    return [
      { name: "Paperless", type: "Documents", href: "https://paperless.kaosgdd.net", meta: "Authoritative document archive" },
      { name: "Wiki.js", type: "Knowledge", href: "https://wiki.kaosgdd.net", meta: "Notes and clinic knowledge" },
      { name: "Memos", type: "Capture", href: "https://memos.kaosgdd.net", meta: "Lightweight memo capture" },
      { name: "SFTPGo", type: "Files", href: "https://files.kaosgdd.net", meta: "Managed file access" },
      { name: "Radicale", type: "Calendar", href: "https://calendar.kaosgdd.net", meta: "Calendar backend candidate" },
      { name: "Vaultwarden", type: "Passwords", href: "https://vault.kaosgdd.net", meta: "Credential vault" },
      { name: "Stirling-PDF", type: "PDF", href: "https://pdf.kaosgdd.net", meta: "PDF workflows" },
      { name: "KaosSupplies", type: "Clinic", href: "https://supplies.kaosgdd.net/docs", meta: "Supplies API" },
      { name: "Fax", type: "Legacy", href: "", meta: "Legacy backend stays alive for now" },
    ];
  },
};

function parseDateTime(value) {
  const raw = String(value || "");
  return {
    date: raw.slice(0, 10),
    time: raw.includes("T") ? raw.slice(11, 16) : "",
  };
}

function normalizeEvent(event) {
  const start = parseDateTime(event.dtstart);
  return {
    id: event.uid,
    date: start.date,
    time: start.time,
    title: event.summary,
    source: event.source || "Radicale",
  };
}

function parseLegacyDescription(description) {
  const lines = String(description || "").split(/\r?\n/);
  const notes = [];
  const subtasks = [];

  lines.forEach((line, index) => {
    if (line.startsWith("-- ")) {
      subtasks.push({ lineIndex: index, done: false, text: line.slice(3) });
    } else if (line.startsWith("-x ")) {
      subtasks.push({ lineIndex: index, done: true, text: line.slice(3) });
    } else {
      notes.push(line);
    }
  });

  return {
    notes: notes.join("\n").trim(),
    subtasks,
  };
}

function taskDescription(task) {
  return state.taskDescriptions[task.uid] || task.description || "";
}

function taskMode(task, done) {
  const categories = new Set((task.categories || []).map((category) => String(category).toLowerCase()));
  if (done) return "done";
  if (categories.has("now") || categories.has("urgent")) return "now";
  if (categories.has("later")) return "later";
  if (task.due === state.selectedDate) return "today";
  return "later";
}

function taskBadge(task, subtasks, done) {
  const categories = new Set((task.categories || []).map((category) => String(category).toLowerCase()));
  if (done) return "";
  if (subtasks.length) {
    const completed = subtasks.filter((subtask) => subtask.done).length;
    return `${completed}/${subtasks.length}`;
  }
  if (categories.has("repeat")) return "R";
  if (task.due === state.selectedDate) return "t";
  return "";
}

function taskMeta(task, parsed, done) {
  if (done && task.completed) return `Done ${parseDateTime(task.completed).time}`;
  const categories = (task.categories || []).filter((category) => !["now", "today", "later", "urgent", "repeat"].includes(category));
  const parts = [];
  if (categories.length) parts.push(categories.join(", "));
  if (task.due) parts.push(task.due === state.selectedDate ? "due today" : `due ${task.due}`);
  if (parsed.subtasks.length) parts.push(`${parsed.subtasks.length} subtasks`);
  return parts.join(" · ") || task.source || "Radicale";
}

function normalizeTask(task) {
  const description = taskDescription(task);
  const parsed = parseLegacyDescription(description);
  const done = task.status === "COMPLETED";
  const categories = new Set((task.categories || []).map((category) => String(category).toLowerCase()));
  return {
    id: task.uid,
    title: task.summary,
    description,
    notes: parsed.notes,
    subtasks: parsed.subtasks,
    meta: taskMeta(task, parsed, done),
    mode: taskMode(task, done),
    done,
    urgent: categories.has("urgent"),
    repeat: categories.has("repeat"),
    badge: taskBadge(task, parsed.subtasks, done),
  };
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function getRoute() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  return routes[raw] ? raw : "today";
}

function ymd(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function monthCells(monthValue) {
  const [year, month] = monthValue.split("-").map(Number);
  const start = new Date(year, month - 1, 1);
  const gridStart = new Date(start);
  gridStart.setDate(start.getDate() - start.getDay());
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart);
    date.setDate(gridStart.getDate() + index);
    return {
      label: String(date.getDate()),
      value: ymd(date),
      muted: date.getMonth() !== month - 1,
    };
  });
}

function routeTitle(route) {
  document.getElementById("routeTitle").textContent = routes[route];
  document.querySelector(".app").dataset.route = route;
  document.querySelectorAll("[data-nav]").forEach((link) => {
    link.classList.toggle("isActive", link.dataset.nav === route);
  });
}

function renderTimeline(events, emptyText = "No items") {
  if (!events.length) {
    return `<div class="panelBody"><p class="taskMeta">${escapeHtml(emptyText)}</p></div>`;
  }
  return `
    <div class="panelBody">
      <ol class="timeline">
        ${events
          .map(
            (event) => `
              <li>
                <time>${escapeHtml(event.time)}</time>
                <div>
                  <strong>${escapeHtml(event.title)}</strong>
                  <span>${escapeHtml(event.source)}</span>
                </div>
              </li>
            `,
          )
          .join("")}
      </ol>
    </div>
  `;
}

function renderTaskRows(tasks) {
  return `
    <ul class="taskList">
      ${tasks
        .map((task) => {
          const done = task.done;
          const classes = ["taskRow", task.urgent ? "isUrgent" : "", task.repeat ? "isRepeat" : "", done ? "isDone" : ""]
            .filter(Boolean)
            .join(" ");
          return `
            <li class="${classes}" data-task-id="${escapeHtml(task.id)}">
              <div class="taskRowMain">
                <button class="checkButton ${done ? "isDone" : ""}" type="button" aria-label="Toggle ${escapeHtml(task.title)}"></button>
                <div>
                  <p class="taskTitle">${escapeHtml(task.title)}</p>
                  <span class="taskMeta">${escapeHtml(task.meta)}</span>
                </div>
                <small class="taskBadge">${escapeHtml(task.badge)}</small>
              </div>
              ${
                task.subtasks.length
                  ? `
                    <ul class="legacySubtasks" aria-label="Subtasks for ${escapeHtml(task.title)}">
                      ${task.subtasks
                        .map(
                          (subtask) => `
                            <li class="${subtask.done ? "isDone" : ""}">
                              <button class="subtaskToggle ${subtask.done ? "isDone" : ""}" type="button" data-subtask-line="${subtask.lineIndex}" aria-label="Toggle ${escapeHtml(subtask.text)}"></button>
                              <span>${escapeHtml(subtask.text)}</span>
                            </li>
                          `,
                        )
                        .join("")}
                    </ul>
                  `
                  : ""
              }
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

function renderToday() {
  const events = mockAdapter.getEvents().filter((event) => event.date === state.selectedDate);
  const tasks = mockAdapter.getTasks().filter((task) => ["now", "today"].includes(task.mode)).slice(0, 4);
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Overview</p>
          <h2>Friday, July 24 · Pohang 21-32 ☀️</h2>
        </div>
      </div>
      <div class="panelBody">
        <div class="summaryGrid">
          <div class="metric"><strong>${events.length}</strong><span>events</span></div>
          <div class="metric"><strong>${tasks.length}</strong><span>tasks</span></div>
          <div class="metric"><strong>7</strong><span>services</span></div>
        </div>
      </div>
    </section>
    <div class="desktopGrid">
      <section class="panel">
        <div class="panelHeader">
          <div>
            <p class="label">Agenda</p>
            <h2>Selected day</h2>
          </div>
          <a class="openButton" href="#/calendar">Open</a>
        </div>
        ${renderTimeline(events)}
      </section>
      <section class="panel">
        <div class="panelHeader">
          <div>
            <p class="label">Tasks</p>
            <h2>Work queue</h2>
          </div>
          <a class="openButton" href="#/tasks">Open</a>
        </div>
        <div class="panelBody">${renderTaskRows(tasks)}</div>
      </section>
    </div>
  `;
}

function renderCalendar() {
  const month = state.selectedDate.slice(0, 7);
  const events = mockAdapter.getEvents();
  const selectedEvents = events.filter((event) => event.date === state.selectedDate);
  const eventDates = new Set(events.map((event) => event.date));
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Calendar</p>
          <h2>July 2026</h2>
        </div>
      </div>
      <div class="calendarGrid" aria-label="Month grid">
        ${["S", "M", "T", "W", "T", "F", "S"].map((day) => `<span class="weekday">${day}</span>`).join("")}
        ${monthCells(month)
          .map((cell) => {
            const classes = [
              "day",
              cell.muted ? "isMuted" : "",
              cell.value === "2026-07-24" ? "isToday" : "",
              cell.value === state.selectedDate ? "isSelected" : "",
              eventDates.has(cell.value) ? "hasEvents" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return `<button class="${classes}" type="button" data-date="${cell.value}">${cell.label}</button>`;
          })
          .join("")}
      </div>
    </section>
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Agenda</p>
          <h2>${escapeHtml(state.selectedDate)}</h2>
        </div>
      </div>
      ${renderTimeline(selectedEvents)}
    </section>
  `;
}

function renderTasks() {
  const tasks = mockAdapter.getTasks().filter((task) => state.taskMode === "all" || task.mode === state.taskMode);
  return `
    <section class="modeRail" aria-label="Task modes">
      ${[
        ["now", "Now"],
        ["today", "Today"],
        ["later", "Later"],
        ["done", "Done"],
        ["all", "All"],
      ]
        .map(
          ([mode, label]) =>
            `<button class="${state.taskMode === mode ? "isActive" : ""}" type="button" data-task-mode="${mode}">${label}</button>`,
        )
        .join("")}
    </section>
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Tasks</p>
          <h2>Work queue</h2>
        </div>
        <button class="openButton" type="button">Add</button>
      </div>
      <div class="panelBody">${renderTaskRows(tasks)}</div>
    </section>
  `;
}

function renderServices() {
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Services</p>
          <h2>Kaos platform</h2>
        </div>
      </div>
      <div class="panelBody">
        <div class="servicesGrid">
          ${mockAdapter
            .getServices()
            .map(
              (service) => `
                <div class="serviceRow">
                  <div>
                    <strong>${escapeHtml(service.name)}</strong>
                    <span class="serviceMeta">${escapeHtml(service.meta)}</span>
                  </div>
                  <div class="serviceActions">
                    <span class="serviceType">${escapeHtml(service.type)}</span>
                    ${
                      service.href
                        ? `<a class="openButton" href="${escapeHtml(service.href)}">Open</a>`
                        : `<span class="openButton" aria-label="No direct service link">Hold</span>`
                    }
                  </div>
                </div>
              `,
            )
            .join("")}
        </div>
      </div>
    </section>
  `;
}

function render() {
  const route = getRoute();
  routeTitle(route);
  const view = document.getElementById("view");
  if (route === "calendar") view.innerHTML = renderCalendar();
  else if (route === "tasks") view.innerHTML = renderTasks();
  else if (route === "services") view.innerHTML = renderServices();
  else view.innerHTML = renderToday();
}

document.addEventListener("click", (event) => {
  const day = event.target.closest("[data-date]");
  if (day) {
    state.selectedDate = day.dataset.date;
    render();
    return;
  }

  const taskMode = event.target.closest("[data-task-mode]");
  if (taskMode) {
    state.taskMode = taskMode.dataset.taskMode;
    render();
    return;
  }

  const check = event.target.closest(".checkButton");
  if (check) {
    const row = check.closest("[data-task-id]");
    if (!row) return;
    const rawTask = mockCalendarData.tasks.find((task) => task.uid === row.dataset.taskId);
    if (!rawTask) return;
    if (rawTask.status === "COMPLETED") {
      rawTask.status = "NEEDS-ACTION";
      delete rawTask.completed;
    } else {
      rawTask.status = "COMPLETED";
      rawTask.completed = `${state.selectedDate}T00:00:00`;
    }
    render();
    return;
  }

  const subtaskToggle = event.target.closest("[data-subtask-line]");
  if (subtaskToggle) {
    const row = subtaskToggle.closest("[data-task-id]");
    const rawTask = mockCalendarData.tasks.find((task) => task.uid === row?.dataset.taskId);
    if (!rawTask) return;

    const lineIndex = Number(subtaskToggle.dataset.subtaskLine);
    const lines = taskDescription(rawTask).split(/\r?\n/);
    const line = lines[lineIndex] || "";
    if (line.startsWith("-- ")) lines[lineIndex] = `-x ${line.slice(3)}`;
    else if (line.startsWith("-x ")) lines[lineIndex] = `-- ${line.slice(3)}`;
    state.taskDescriptions[rawTask.uid] = lines.join("\n");
    render();
  }
});

window.addEventListener("hashchange", render);

if (!window.location.hash) {
  window.location.hash = "#/today";
} else {
  render();
}
