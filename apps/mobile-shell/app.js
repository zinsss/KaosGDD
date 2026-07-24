const routes = {
  today: "Today",
  calendar: "Calendar",
  tasks: "Tasks",
  services: "Services",
};

const state = {
  selectedDate: "2026-07-24",
  taskMode: "now",
  taskDone: new Set(["paperless-inbox"]),
};

const mockAdapter = {
  getEvents() {
    return [
      { id: "vaccine-prep", date: "2026-07-24", time: "09:00", title: "Vaccine room prep", source: "Clinic" },
      { id: "supplies-review", date: "2026-07-24", time: "11:30", title: "Supplies review", source: "KaosSupplies" },
      { id: "roun-check", date: "2026-07-24", time: "17:00", title: "ROUN timetable check", source: "Family" },
      { id: "scan-review", date: "2026-07-27", time: "10:00", title: "Scan queue review", source: "PACS" },
      { id: "paperless-cleanup", date: "2026-07-30", time: "15:00", title: "Paperless archive pass", source: "Documents" },
    ];
  },

  getTasks() {
    return [
      {
        id: "fax-result",
        title: "Review incoming fax result",
        meta: "Fax bridge · due now",
        mode: "now",
        urgent: true,
        badge: "+",
      },
      {
        id: "scan-queue",
        title: "Check scan queue",
        meta: "PACS adapter · 2 subtasks",
        mode: "now",
        badge: "2/4",
      },
      {
        id: "supply-sync",
        title: "Daily supply sync",
        meta: "KaosSupplies · repeats",
        mode: "today",
        repeat: true,
        badge: "R",
      },
      {
        id: "roun-window",
        title: "Confirm ROUN timetable window",
        meta: "Family · standalone module",
        mode: "today",
        badge: "t",
      },
      {
        id: "paperless-inbox",
        title: "Paperless inbox check",
        meta: "Done 08:40",
        mode: "done",
        badge: "",
      },
      {
        id: "wiki-note",
        title: "Move protocol notes to Wiki.js",
        meta: "Knowledge · later",
        mode: "later",
        badge: "#",
      },
    ];
  },

  getServices() {
    return [
      { name: "Paperless", type: "Documents", href: "https://paperless.kaosgdd.net", meta: "Authoritative document archive" },
      { name: "Wiki.js", type: "Knowledge", href: "https://wiki.kaosgdd.net", meta: "Notes and clinic knowledge" },
      { name: "SFTPGo", type: "Files", href: "https://files.kaosgdd.net", meta: "Managed file access" },
      { name: "Radicale", type: "Calendar", href: "https://calendar.kaosgdd.net", meta: "Calendar backend candidate" },
      { name: "Vaultwarden", type: "Passwords", href: "https://vault.kaosgdd.net", meta: "Credential vault" },
      { name: "Stirling-PDF", type: "PDF", href: "https://pdf.kaosgdd.net", meta: "PDF workflows" },
      { name: "KaosSupplies", type: "Clinic", href: "https://supplies.kaosgdd.net/docs", meta: "Supplies API" },
      { name: "Fax", type: "Legacy", href: "", meta: "Legacy backend stays alive for now" },
    ];
  },
};

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
          const done = state.taskDone.has(task.id) || task.mode === "done";
          const classes = ["taskRow", task.urgent ? "isUrgent" : "", task.repeat ? "isRepeat" : "", done ? "isDone" : ""]
            .filter(Boolean)
            .join(" ");
          return `
            <li class="${classes}" data-task-id="${escapeHtml(task.id)}">
              <button class="checkButton ${done ? "isDone" : ""}" type="button" aria-label="Toggle ${escapeHtml(task.title)}"></button>
              <div>
                <p class="taskTitle">${escapeHtml(task.title)}</p>
                <span class="taskMeta">${escapeHtml(task.meta)}</span>
              </div>
              <small class="taskBadge">${escapeHtml(task.badge)}</small>
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
          <h2>Friday, July 24 · Seoul 22 C</h2>
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
    if (state.taskDone.has(row.dataset.taskId)) state.taskDone.delete(row.dataset.taskId);
    else state.taskDone.add(row.dataset.taskId);
    render();
  }
});

window.addEventListener("hashchange", render);

if (!window.location.hash) {
  window.location.hash = "#/today";
} else {
  render();
}
