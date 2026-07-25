const routes = {
  today: "Today",
  calendar: "Calendar",
  tasks: "Tasks",
  services: "Services",
};

const state = {
  selectedDate: "2026-07-24",
  currentCollection: "family",
  taskMode: "now",
  eventComposerOpen: false,
  taskComposerOpen: false,
  taskDescriptions: {},
  remoteCalendar: {
    checked: false,
    configured: false,
    live: false,
    error: "",
    collections: [],
    events: [],
    tasks: [],
  },
};

const mockCalendarData = {
  collections: [
    { id: "family", name: "Family", owner: "family", color: "nord14" },
    { id: "zin", name: "Zin", owner: "zin", color: "nord8" },
  ],
  events: [
    { uid: "vaccine-prep", collection: "zin", summary: "Vaccine room prep", dtstart: "2026-07-24T09:00:00", source: "Clinic" },
    { uid: "supplies-review", collection: "zin", summary: "Supplies review", dtstart: "2026-07-24T11:30:00", source: "KaosSupplies" },
    { uid: "roun-check", collection: "family", summary: "ROUN timetable check", dtstart: "2026-07-24T17:00:00", source: "Family" },
    { uid: "family-dinner", collection: "family", summary: "Family dinner", dtstart: "2026-07-24T18:30:00", source: "Family" },
    { uid: "scan-review", collection: "zin", summary: "Scan queue review", dtstart: "2026-07-27T10:00:00", source: "PACS" },
    { uid: "paperless-cleanup", collection: "zin", summary: "Paperless archive pass", dtstart: "2026-07-30T15:00:00", source: "Documents" },
  ],
  tasks: [
    {
      uid: "fax-result",
      collection: "zin",
      summary: "Review incoming fax result",
      description: "Fax follow-up notes\n\n-- confirm sender\n-- attach PDF\n-x send fax notification",
      due: "2026-07-24",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T08:35:00",
      categories: ["fax", "now", "urgent"],
      source: "Radicale mock",
    },
    {
      uid: "scan-queue",
      collection: "zin",
      summary: "Check scan queue",
      description: "PACS check\n\n-- review failed imports\n-- confirm scan queue",
      due: "2026-07-24",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T08:20:00",
      categories: ["pacs", "now"],
      source: "Radicale mock",
    },
    {
      uid: "supply-sync",
      collection: "zin",
      summary: "Daily supply sync",
      description: "Daily repeat\n\n-- compare low-stock list\n-- update order note",
      due: "2026-07-24",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T07:50:00",
      categories: ["supplies", "today", "repeat"],
      source: "Radicale mock",
    },
    {
      uid: "roun-window",
      collection: "family",
      summary: "Confirm ROUN timetable window",
      description: "Standalone family module\n\n-- check school pickup window",
      due: "2026-07-24",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T07:30:00",
      categories: ["family", "today"],
      source: "Radicale mock",
    },
    {
      uid: "paperless-inbox",
      collection: "zin",
      summary: "Paperless inbox check",
      description: "Inbox cleared at 08:40\n\n-x archive complete",
      due: "2026-07-24",
      status: "COMPLETED",
      completed: "2026-07-24T08:40:00",
      lastModified: "2026-07-24T08:40:00",
      categories: ["documents"],
      source: "Radicale mock",
    },
    {
      uid: "wiki-note",
      collection: "zin",
      summary: "Move protocol notes to Wiki.js",
      description: "Knowledge cleanup\n\n-- move vaccine protocol\n-- link from KaosGDD",
      due: "2026-07-30",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T06:10:00",
      categories: ["knowledge", "later"],
      source: "Radicale mock",
    },
  ],
};

const mockAdapter = {
  getCollections() {
    return activeCalendarData().collections;
  },

  getCurrentCollection() {
    return activeCalendarData().collections.find((collection) => collection.id === state.currentCollection);
  },

  getEvents(collectionId = state.currentCollection) {
    return activeCalendarData().events.filter((event) => event.collection === collectionId).map(normalizeEvent).sort(sortByDateTime);
  },

  getTasks(collectionId = state.currentCollection) {
    return activeCalendarData().tasks.filter((task) => task.collection === collectionId).map(normalizeTask).sort(sortTasks);
  },

  createEvent(formData) {
    const title = String(formData.get("title") || "").trim();
    if (!title) return;
    const date = String(formData.get("date") || state.selectedDate);
    const time = String(formData.get("time") || "09:00");
    activeCalendarData().events.push({
      uid: `event-${Date.now()}`,
      collection: state.currentCollection,
      summary: title,
      dtstart: `${date}T${time}:00`,
      source: this.getCurrentCollection()?.name || "Radicale",
    });
    state.selectedDate = date;
    state.eventComposerOpen = false;
  },

  createTask(formData) {
    const title = String(formData.get("title") || "").trim();
    if (!title) return;
    const notes = String(formData.get("notes") || "").trim();
    const rawSubtasks = String(formData.get("subtasks") || "").trim();
    const subtasks = rawSubtasks
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => (line.startsWith("-- ") || line.startsWith("-x ") ? line : `-- ${line}`));
    const description = [notes, subtasks.join("\n")].filter(Boolean).join("\n\n");
    activeCalendarData().tasks.push({
      uid: `task-${Date.now()}`,
      collection: state.currentCollection,
      summary: title,
      description,
      due: String(formData.get("due") || state.selectedDate),
      status: "NEEDS-ACTION",
      lastModified: new Date().toISOString().slice(0, 19),
      categories: String(formData.get("mode") || "today")
        .split(",")
        .map((category) => category.trim())
        .filter(Boolean),
      source: "Radicale draft",
    });
    state.taskMode = "all";
    state.taskComposerOpen = false;
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

function activeCalendarData() {
  if (state.remoteCalendar.live && state.remoteCalendar.collections.length) {
    return state.remoteCalendar;
  }
  return mockCalendarData;
}

async function loadRemoteCalendar() {
  try {
    const response = await fetch("/api/calendar/bootstrap", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.remoteCalendar = {
      checked: true,
      configured: Boolean(payload.configured),
      live: Boolean(payload.live && payload.collections?.length),
      error: "",
      collections: payload.collections || [],
      events: payload.events || [],
      tasks: payload.tasks || [],
    };
    if (state.remoteCalendar.live && !state.remoteCalendar.collections.some((collection) => collection.id === state.currentCollection)) {
      state.currentCollection = state.remoteCalendar.collections[0].id;
    }
  } catch (error) {
    state.remoteCalendar = {
      ...state.remoteCalendar,
      checked: true,
      live: false,
      error: error.message || "Calendar adapter unavailable",
    };
  }
  render();
}

function parseDateTime(value) {
  const raw = String(value || "");
  return {
    date: raw.slice(0, 10),
    time: raw.includes("T") ? raw.slice(11, 16) : "",
  };
}

function formatDateTimeLabel(value) {
  const parsed = parseDateTime(value);
  if (!parsed.date) return "";
  if (parsed.date === state.selectedDate && parsed.time) return `modified ${parsed.time}`;
  return parsed.time ? `modified ${parsed.date} ${parsed.time}` : `modified ${parsed.date}`;
}

function normalizeEvent(event) {
  if (event.date) {
    return {
      id: event.id || event.uid,
      collection: event.collection,
      date: event.date,
      time: event.time || "",
      title: event.title || event.summary || "Untitled event",
      source: event.source || "Radicale",
    };
  }
  const start = parseDateTime(event.dtstart);
  const collection = activeCalendarData().collections.find((item) => item.id === event.collection);
  return {
    id: event.uid,
    collection: event.collection,
    date: start.date,
    time: start.time,
    title: event.summary,
    source: `${collection?.name || "Radicale"} · ${event.source || "Radicale"}`,
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
  if (!task.due) return "now";
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
  const collection = activeCalendarData().collections.find((item) => item.id === task.collection);
  if (done && task.completed) return `Done ${parseDateTime(task.completed).time}`;
  const categories = (task.categories || []).filter((category) => !["now", "today", "later", "urgent", "repeat"].includes(category));
  const parts = [];
  if (collection) parts.push(collection.name);
  if (categories.length) parts.push(categories.join(", "));
  if (task.due) parts.push(task.due === state.selectedDate ? "due today" : `due ${task.due}`);
  else if (task.lastModified || task.created) parts.push(formatDateTimeLabel(task.lastModified || task.created));
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
    collection: task.collection,
    title: task.summary,
    description,
    due: task.due || "",
    lastModified: task.lastModified || task.created || "",
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

function sortByDateTime(a, b) {
  return `${a.date}T${a.time || "00:00"}`.localeCompare(`${b.date}T${b.time || "00:00"}`);
}

function sortTasks(a, b) {
  if (a.done !== b.done) return a.done ? 1 : -1;
  if (a.due && b.due && a.due !== b.due) return a.due.localeCompare(b.due);
  if (a.due && !b.due) return -1;
  if (!a.due && b.due) return 1;
  if (!a.due && !b.due) return (b.lastModified || "").localeCompare(a.lastModified || "");
  return a.title.localeCompare(b.title);
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

function renderCollectionRail() {
  return `
    <section class="collectionRail" aria-label="Radicale collections">
      ${mockAdapter
        .getCollections()
        .map(
          (collection) => `
            <button class="${state.currentCollection === collection.id ? "isActive" : ""}" type="button" data-collection="${escapeHtml(collection.id)}">
              <span>${escapeHtml(collection.name)}</span>
              <small>${escapeHtml(collection.owner)}</small>
            </button>
          `,
        )
        .join("")}
    </section>
  `;
}

function renderRadicaleStatus() {
  const collection = mockAdapter.getCurrentCollection();
  const remote = state.remoteCalendar;
  const status = remote.live
    ? "Live Radicale read-only"
    : remote.checked && remote.configured
      ? "No live collection found · local preview"
      : remote.checked && remote.error
        ? "Adapter unavailable · local preview"
        : "Local preview · CalDAV write adapter pending";
  return `
    <section class="adapterNote" aria-label="Radicale adapter status">
      <strong>${escapeHtml(collection?.name || "Radicale")}</strong>
      <span>${escapeHtml(status)}</span>
    </section>
  `;
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
    ${renderCollectionRail()}
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
    ${renderCollectionRail()}
    ${renderRadicaleStatus()}
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Calendar</p>
          <h2>July 2026</h2>
        </div>
        <button class="openButton" type="button" data-toggle-event-composer>${state.eventComposerOpen ? "Close" : "Add"}</button>
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
    ${state.eventComposerOpen ? renderEventComposer() : ""}
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
    ${renderCollectionRail()}
    ${renderRadicaleStatus()}
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
        <button class="openButton" type="button" data-toggle-task-composer>${state.taskComposerOpen ? "Close" : "Add"}</button>
      </div>
      ${state.taskComposerOpen ? renderTaskComposer() : ""}
      <div class="panelBody">${renderTaskRows(tasks)}</div>
    </section>
  `;
}

function renderEventComposer() {
  return `
    <section class="panel">
      <form class="composer" data-create-event>
        <label>
          <span>Event</span>
          <input name="title" type="text" autocomplete="off" placeholder="New event" required />
        </label>
        <div class="formGrid">
          <label>
            <span>Date</span>
            <input name="date" type="date" value="${escapeHtml(state.selectedDate)}" required />
          </label>
          <label>
            <span>Time</span>
            <input name="time" type="time" value="09:00" step="300" required />
          </label>
        </div>
        <button class="primaryButton" type="submit">Create local event</button>
      </form>
    </section>
  `;
}

function renderTaskComposer() {
  return `
    <form class="composer" data-create-task>
      <label>
        <span>Task</span>
        <input name="title" type="text" autocomplete="off" placeholder="New task" required />
      </label>
      <div class="formGrid">
        <label>
          <span>Due</span>
          <input name="due" type="date" value="${escapeHtml(state.selectedDate)}" />
        </label>
        <label>
          <span>Mode</span>
          <select name="mode">
            <option value="now">Now</option>
            <option value="today" selected>Today</option>
            <option value="later">Later</option>
          </select>
        </label>
      </div>
      <label>
        <span>Notes</span>
        <textarea name="notes" rows="2" placeholder="Description"></textarea>
      </label>
      <label>
        <span>Subtasks</span>
        <textarea name="subtasks" rows="3" placeholder="one per line; saved as -- subtask"></textarea>
      </label>
      <button class="primaryButton" type="submit">Create local task</button>
    </form>
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

  const collection = event.target.closest("[data-collection]");
  if (collection) {
    state.currentCollection = collection.dataset.collection;
    render();
    return;
  }

  if (event.target.closest("[data-toggle-event-composer]")) {
    state.eventComposerOpen = !state.eventComposerOpen;
    render();
    return;
  }

  if (event.target.closest("[data-toggle-task-composer]")) {
    state.taskComposerOpen = !state.taskComposerOpen;
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

document.addEventListener("submit", (event) => {
  const eventForm = event.target.closest("[data-create-event]");
  if (eventForm) {
    event.preventDefault();
    mockAdapter.createEvent(new FormData(eventForm));
    render();
    return;
  }

  const taskForm = event.target.closest("[data-create-task]");
  if (taskForm) {
    event.preventDefault();
    mockAdapter.createTask(new FormData(taskForm));
    render();
  }
});

window.addEventListener("hashchange", render);

if (!window.location.hash) {
  window.location.hash = "#/today";
} else {
  render();
}

loadRemoteCalendar();
