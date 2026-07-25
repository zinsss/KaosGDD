const routes = {
  today: "Today",
  calendar: "Calendar",
  tasks: "Tasks",
  add: "Add",
  "add-event": "Add Event",
  "add-task": "Add Task",
  "edit-task": "Edit Task",
  services: "Services",
};

const DEFAULT_TASK_DUE_TIME = "10:00";
const DEFAULT_EVENT_START_TIME = "09:00";
const DEFAULT_EVENT_END_TIME = "10:00";

const taskPriorityOptions = {
  none: { value: "", label: "None", rank: 10 },
  low: { value: "9", label: "Low", rank: 9 },
  medium: { value: "5", label: "Medium", rank: 5 },
  high: { value: "1", label: "High", rank: 1 },
};

const state = {
  selectedDate: ymd(new Date()),
  currentCollection: "all",
  taskMode: "active",
  taskSort: "due",
  addKind: "event",
  addMonthExpanded: false,
  taskDueEnabled: false,
  editingTaskId: "",
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
    { uid: "vaccine-prep", collection: "zin", summary: "Vaccine room prep", dtstart: "2026-07-24T09:00:00" },
    { uid: "supplies-review", collection: "zin", summary: "Supplies review", dtstart: "2026-07-24T11:30:00" },
    { uid: "roun-check", collection: "family", summary: "ROUN timetable check", dtstart: "2026-07-24T17:00:00" },
    { uid: "family-dinner", collection: "family", summary: "Family dinner", dtstart: "2026-07-24T18:30:00" },
    { uid: "scan-review", collection: "zin", summary: "Scan queue review", dtstart: "2026-07-27T10:00:00" },
    { uid: "paperless-cleanup", collection: "zin", summary: "Paperless archive pass", dtstart: "2026-07-30T15:00:00" },
  ],
  tasks: [
    {
      uid: "fax-result",
      collection: "zin",
      summary: "Review incoming fax result",
      description: "Fax follow-up notes\n\n-- confirm sender\n-- attach PDF\n-x send fax notification",
      due: "2026-07-24",
      dueTime: "10:00",
      priority: "1",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T08:35:00",
      categories: ["fax"],
    },
    {
      uid: "scan-queue",
      collection: "zin",
      summary: "Check scan queue",
      description: "PACS check\n\n-- review failed imports\n-- confirm scan queue",
      due: "2026-07-24",
      dueTime: "10:00",
      priority: "5",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T08:20:00",
      categories: ["pacs"],
    },
    {
      uid: "supply-sync",
      collection: "zin",
      summary: "Daily supply sync",
      description: "Daily repeat\n\n-- compare low-stock list\n-- update order note",
      due: "2026-07-24",
      dueTime: "10:00",
      priority: "9",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T07:50:00",
      categories: ["supplies"],
    },
    {
      uid: "roun-window",
      collection: "family",
      summary: "Confirm ROUN timetable window",
      description: "Standalone family module\n\n-- check school pickup window",
      due: "2026-07-24",
      dueTime: "10:00",
      priority: "",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T07:30:00",
      categories: ["family"],
    },
    {
      uid: "paperless-inbox",
      collection: "zin",
      summary: "Paperless inbox check",
      description: "Inbox cleared at 08:40\n\n-x archive complete",
      due: "2026-07-24",
      dueTime: "08:40",
      priority: "",
      status: "COMPLETED",
      completed: "2026-07-24T08:40:00",
      lastModified: "2026-07-24T08:40:00",
      categories: ["documents"],
    },
    {
      uid: "wiki-note",
      collection: "zin",
      summary: "Move protocol notes to Wiki.js",
      description: "Knowledge cleanup\n\n-- move vaccine protocol\n-- link from KaosGDD",
      due: "2026-07-30",
      dueTime: "10:00",
      priority: "5",
      status: "NEEDS-ACTION",
      lastModified: "2026-07-24T06:10:00",
      categories: ["knowledge"],
    },
  ],
};

const mockAdapter = {
  getCollections() {
    return collectionViews();
  },

  getCurrentCollection() {
    return collectionViews().find((collection) => collection.id === state.currentCollection);
  },

  getEvents(collectionId = state.currentCollection) {
    return filterByCollectionView(activeCalendarData().events, collectionId).map(normalizeEvent).sort(sortByDateTime);
  },

  getTasks(collectionId = state.currentCollection) {
    return filterByCollectionView(activeCalendarData().tasks, collectionId).map(normalizeTask).sort(sortTasks);
  },

  createEvent(formData) {
    const title = String(formData.get("title") || "").trim();
    if (!title) return;
    const allDay = formData.get("allDay") === "on";
    const startDate = String(formData.get("startDate") || state.selectedDate);
    const endDate = String(formData.get("endDate") || startDate);
    const startTime = String(formData.get("startTime") || DEFAULT_EVENT_START_TIME);
    const endTime = String(formData.get("endTime") || DEFAULT_EVENT_END_TIME);
    activeCalendarData().events.push({
      uid: `event-${Date.now()}`,
      collection: writableCollectionId(),
      summary: title,
      description: String(formData.get("memo") || "").trim(),
      dtstart: allDay ? startDate : `${startDate}T${startTime}:00`,
      dtend: allDay ? endDate : `${endDate}T${endTime}:00`,
      allDay,
      repeat: String(formData.get("repeat") || ""),
      alarm: String(formData.get("alarm") || ""),
    });
    state.selectedDate = startDate;
  },

  createTask(formData) {
    const title = String(formData.get("title") || "").trim();
    if (!title) return;
    const description = String(formData.get("memo") || "").trim();
    const due = taskDueFromForm(formData);
    activeCalendarData().tasks.push({
      uid: `task-${Date.now()}`,
      collection: writableCollectionId(),
      summary: title,
      description,
      due: due.date,
      dueTime: due.time,
      priority: taskPriorityFromForm(formData),
      status: "NEEDS-ACTION",
      lastModified: new Date().toISOString().slice(0, 19),
      categories: [],
    });
    state.taskMode = "active";
  },

  updateTask(formData) {
    const uid = String(formData.get("uid") || "");
    const rawTask = activeCalendarData().tasks.find((task) => task.uid === uid);
    if (!rawTask) return;
    const title = String(formData.get("title") || "").trim();
    if (!title) return;
    const due = taskDueFromForm(formData);
    rawTask.summary = title;
    rawTask.description = String(formData.get("memo") || "").trim();
    rawTask.due = due.date;
    rawTask.dueTime = due.time;
    rawTask.priority = taskPriorityFromForm(formData);
    rawTask.lastModified = new Date().toISOString().slice(0, 19);
    state.taskMode = rawTask.status === "COMPLETED" ? "done" : "active";
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

function collectionViews() {
  const data = activeCalendarData();
  const allIds = data.collections.map((collection) => collection.id);
  const familyIds = data.collections.filter((collection) => collection.owner === "family" || collection.id === "family").map((collection) => collection.id);
  const zinIds = data.collections.filter((collection) => collection.owner === "zin" || collection.id === "zin").map((collection) => collection.id);
  return [
    { id: "all", name: "All", owner: "Radicale", collectionIds: allIds },
    { id: "family", name: "Family", owner: "shared", collectionIds: familyIds },
    { id: "gdd_zin", name: "GDD_ZiN", owner: "zin", collectionIds: zinIds },
  ];
}

function filterByCollectionView(items, viewId) {
  const view = collectionViews().find((collection) => collection.id === viewId) || collectionViews()[0];
  if (view.id === "all") return items;
  return items.filter((item) => view.collectionIds.includes(item.collection));
}

function writableCollectionId() {
  const view = mockAdapter.getCurrentCollection();
  if (view?.id !== "all" && view?.collectionIds.length) return view.collectionIds[0];
  return activeCalendarData().collections[0]?.id || "zin";
}

function writableTaskCollectionId() {
  const data = activeCalendarData();
  const view = mockAdapter.getCurrentCollection();
  const collectionIds = view?.id !== "all" && view?.collectionIds.length
    ? view.collectionIds
    : data.collections.map((collection) => collection.id);
  const taskCollectionIds = new Set(data.tasks.map((task) => task.collection));
  const taskCollection = data.collections.find((collection) => collectionIds.includes(collection.id) && taskCollectionIds.has(collection.id));
  if (taskCollection) return taskCollection.id;
  const namedTaskCollection = data.collections.find((collection) => collectionIds.includes(collection.id) && /task|reminder/i.test(collection.name));
  if (namedTaskCollection) return namedTaskCollection.id;
  return collectionIds[0] || writableCollectionId();
}

function findTaskById(taskId) {
  return activeCalendarData().tasks.map(normalizeTask).find((task) => task.id === taskId);
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
    if (state.remoteCalendar.live && !collectionViews().some((collection) => collection.id === state.currentCollection)) {
      state.currentCollection = "all";
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

async function createRemoteTask(formData) {
  const due = taskDueFromForm(formData);
  const response = await fetch("/api/calendar/tasks", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      collectionId: writableTaskCollectionId(),
      title: String(formData.get("title") || "").trim(),
      memo: String(formData.get("memo") || "").trim(),
      dueDate: due.date,
      dueTime: due.time,
      priority: taskPriorityFromForm(formData),
    }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  state.taskMode = "active";
  window.location.hash = "#/tasks";
  await loadRemoteCalendar();
}

async function updateRemoteTask(formData) {
  const due = taskDueFromForm(formData);
  const response = await fetch("/api/calendar/tasks", {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      uid: String(formData.get("uid") || ""),
      collectionId: String(formData.get("collectionId") || ""),
      title: String(formData.get("title") || "").trim(),
      memo: String(formData.get("memo") || "").trim(),
      dueDate: due.date,
      dueTime: due.time,
      priority: taskPriorityFromForm(formData),
    }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  window.location.hash = "#/tasks";
  await loadRemoteCalendar();
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
      detail: event.location || event.description || "",
    };
  }
  const start = parseDateTime(event.dtstart);
  const end = parseDateTime(event.dtend);
  const allDay = Boolean(event.allDay || (event.dtstart && !String(event.dtstart).includes("T")));
  return {
    id: event.uid,
    collection: event.collection,
    date: start.date,
    time: allDay ? "" : start.time,
    endDate: end.date,
    endTime: allDay ? "" : end.time,
    allDay,
    title: event.summary,
    detail: event.location || event.description || "",
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

function taskDueFromForm(formData) {
  const rawDue = String(formData.get("due") || "");
  const rawTime = String(formData.get("dueTime") || "").trim();
  const date = rawDue;
  const time = date ? rawTime || DEFAULT_TASK_DUE_TIME : "";
  return { date, time };
}

function taskDueHasPassed(due) {
  if (!due.date || !due.time) return false;
  return new Date(`${due.date}T${due.time}:00`).getTime() < Date.now();
}

function taskPriorityFromForm(formData) {
  const priority = String(formData.get("priority") || "");
  return Object.values(taskPriorityOptions).some((option) => option.value === priority) ? priority : "";
}

function taskPriorityRank(priority) {
  const value = Number(priority);
  if (!Number.isInteger(value) || value < 1 || value > 9) return taskPriorityOptions.none.rank;
  return value;
}

function taskPriorityLabel(priority) {
  const rank = taskPriorityRank(priority);
  if (rank <= 3) return "High";
  if (rank <= 6) return "Medium";
  if (rank <= 9) return "Low";
  return "";
}

function taskPriorityMark(priority) {
  const rank = taskPriorityRank(priority);
  if (rank <= 3) return "!!!";
  if (rank <= 6) return "!!";
  if (rank <= 9) return "!";
  return "";
}

function taskBucket(task, done) {
  if (done) return "done";
  if (task.due) return "dated";
  return "inbox";
}

function taskBadge(task, subtasks, done) {
  if (done) return "";
  const badgeParts = [];
  const priority = taskPriorityMark(task.priority);
  if (priority) badgeParts.push(priority);
  if (subtasks.length) {
    const completed = subtasks.filter((subtask) => subtask.done).length;
    badgeParts.push(`${completed}/${subtasks.length}`);
  }
  return badgeParts.join(" · ");
}

function taskMeta(task, parsed, done) {
  if (done && task.completed) return `Done ${parseDateTime(task.completed).time}`;
  const parts = [];
  if (task.due) {
    const dueDate = task.due === state.selectedDate ? "due today" : `due ${task.due}`;
    parts.push(task.dueTime ? `${dueDate} ${task.dueTime}` : dueDate);
  }
  else if (task.lastModified || task.created) parts.push(formatDateTimeLabel(task.lastModified || task.created));
  if (parsed.subtasks.length) parts.push(`${parsed.subtasks.length} subtasks`);
  return parts.join(" · ");
}

function normalizeTask(task) {
  const description = taskDescription(task);
  const parsed = parseLegacyDescription(description);
  const done = task.status === "COMPLETED";
  return {
    id: task.uid,
    collection: task.collection,
    title: task.summary,
    description,
    due: task.due || "",
    dueTime: task.dueTime || "",
    priority: task.priority || "",
    priorityRank: taskPriorityRank(task.priority),
    priorityLabel: taskPriorityLabel(task.priority),
    priorityMark: taskPriorityMark(task.priority),
    created: task.created || "",
    lastModified: task.lastModified || task.created || "",
    notes: parsed.notes,
    subtasks: parsed.subtasks,
    meta: taskMeta(task, parsed, done),
    mode: taskBucket(task, done),
    done,
    badge: taskBadge(task, parsed.subtasks, done),
  };
}

function sortByDateTime(a, b) {
  return `${a.date}T${a.time || "00:00"}`.localeCompare(`${b.date}T${b.time || "00:00"}`);
}

function sortTasks(a, b) {
  if (a.done !== b.done) return a.done ? 1 : -1;
  if (state.taskSort === "created") return compareTasksByCreated(a, b);
  return compareTasksByDue(a, b);
}

function compareTasksByCreated(a, b) {
  const created = (a.created || a.lastModified || "").localeCompare(b.created || b.lastModified || "");
  if (created) return created;
  return a.title.localeCompare(b.title);
}

function compareTasksByDue(a, b) {
  if (a.due && b.due && a.due !== b.due) return a.due.localeCompare(b.due);
  if (a.due && b.due && a.dueTime !== b.dueTime) return (a.dueTime || "99:99").localeCompare(b.dueTime || "99:99");
  if (a.due && b.due) return compareTasksByCreated(a, b);
  if (a.due && !b.due) return -1;
  if (!a.due && b.due) return 1;
  if (!a.due && !b.due) return compareTasksByCreated(a, b);
  return a.title.localeCompare(b.title);
}

function taskMatchesMode(task, mode) {
  if (mode === "active") return !task.done;
  if (mode === "all") return true;
  return task.mode === mode;
}

function groupTasksByDue(tasks) {
  return tasks.reduce((groups, task) => {
    const due = task.due || "No due date";
    if (!groups[due]) groups[due] = [];
    groups[due].push(task);
    return groups;
  }, {});
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
  const route = raw.split("?", 1)[0];
  return routes[route] ? route : "today";
}

function hashParam(name) {
  const query = window.location.hash.split("?", 2)[1] || "";
  return new URLSearchParams(query).get(name) || "";
}

function ymd(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function compactDateLabel(dateValue) {
  const date = new Date(`${dateValue}T00:00:00`);
  const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return `${dateValue.replace(/-/g, ".")} ${weekdays[date.getDay()]}`;
}

function monthTitle(monthValue) {
  const [year, month] = monthValue.split("-").map(Number);
  const date = new Date(year, month - 1, 1);
  return `${date.toLocaleString("en", { month: "long" })} ${year}`;
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

function addPageCells(monthValue) {
  const cells = monthCells(monthValue);
  if (state.addMonthExpanded) return cells;
  const selectedIndex = cells.findIndex((cell) => cell.value === state.selectedDate);
  const start = Math.max(0, Math.floor((selectedIndex < 0 ? 0 : selectedIndex) / 7) * 7);
  return cells.slice(start, start + 7);
}

function routeTitle(route) {
  const title = route === "add-event" || route === "add-task" ? routes.add : routes[route];
  document.getElementById("routeTitle").textContent = title;
  document.querySelector(".app").dataset.route = route;
  document.querySelectorAll("[data-nav]").forEach((link) => {
    const activeRoute = route === "add" || route === "add-event" ? "calendar" : route === "add-task" || route === "edit-task" ? "tasks" : route;
    link.classList.toggle("isActive", link.dataset.nav === activeRoute);
  });
}

function renderAddDatePicker({ title, allowNoDate = false }) {
  const month = state.selectedDate.slice(0, 7);
  const cells = addPageCells(month);
  const dueEnabled = state.taskDueEnabled;
  const dueLabel = dueEnabled ? `Due ${state.selectedDate}` : "No due date";
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">${escapeHtml(title)}</p>
          <h2>${escapeHtml(monthTitle(month))}</h2>
        </div>
        <button class="openButton" type="button" data-toggle-add-month>${state.addMonthExpanded ? "Collapse" : "Month"}</button>
      </div>
      <div class="calendarGrid addCalendarGrid ${state.addMonthExpanded ? "isExpanded" : "isCollapsed"}" aria-label="${escapeHtml(title)}">
        ${["S", "M", "T", "W", "T", "F", "S"].map((day) => `<span class="weekday">${day}</span>`).join("")}
        ${cells
          .map((cell) => {
            const classes = [
              "day",
              cell.muted ? "isMuted" : "",
              cell.value === ymd(new Date()) ? "isToday" : "",
              cell.value === state.selectedDate ? "isSelected" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return `<button class="${classes}" type="button" data-date="${cell.value}">${cell.label}</button>`;
          })
          .join("")}
      </div>
      ${
        allowNoDate
          ? `
            <div class="panelBody slimBody duePickerRow">
              <span class="formNote">${escapeHtml(dueLabel)}</span>
              ${
                dueEnabled
                  ? `<button class="iconTextButton" type="button" data-clear-task-due aria-label="Clear due date">x</button>`
                  : `<button class="plainButton" type="button" data-use-selected-due>Use selected date</button>`
              }
            </div>
          `
          : ""
      }
    </section>
  `;
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
                  ${event.detail ? `<span>${escapeHtml(event.detail)}</span>` : ""}
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
  if (!tasks.length) {
    return `<p class="taskMeta">No tasks</p>`;
  }
  return `
    <ul class="taskList">
      ${tasks
        .map((task) => {
          const done = task.done;
          const classes = ["taskRow", task.priorityLabel ? `priority${task.priorityLabel}` : "", done ? "isDone" : ""].filter(Boolean).join(" ");
          return `
            <li class="${classes}" data-task-id="${escapeHtml(task.id)}">
              <div class="taskRowMain">
                <button class="checkButton ${done ? "isDone" : ""}" type="button" aria-label="Toggle ${escapeHtml(task.title)}"></button>
                <a class="taskEditLink" href="#/edit-task?uid=${encodeURIComponent(task.id)}">
                  <p class="taskTitle">${escapeHtml(task.title)}</p>
                  <span class="taskMeta">${escapeHtml(task.meta)}</span>
                </a>
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

function renderTaskGroups(tasks) {
  if (!tasks.length) return `<p class="taskMeta">No dated tasks</p>`;
  const groups = groupTasksByDue(tasks);
  return Object.keys(groups)
    .sort()
    .map(
      (due) => `
        <section class="taskGroup">
          <h3 class="taskGroupTitle">${escapeHtml(due)}</h3>
          ${renderTaskRows(groups[due])}
        </section>
      `,
    )
    .join("");
}

function renderCalendarAgenda(events, tasks) {
  if (!events.length && !tasks.length) {
    return `<div class="panelBody"><p class="taskMeta">No items</p></div>`;
  }
  return `
    ${events.length ? renderTimeline(events, "") : ""}
    ${
      tasks.length
        ? `
          <div class="panelBody ${events.length ? "withDivider" : ""}">
            <p class="label sectionLabel">Tasks due</p>
            ${renderTaskRows(tasks)}
          </div>
        `
        : ""
    }
  `;
}

function renderToday() {
  const events = mockAdapter.getEvents().filter((event) => event.date === state.selectedDate);
  const tasks = mockAdapter
    .getTasks()
    .filter((task) => task.mode === "inbox" || task.due === state.selectedDate)
    .slice(0, 4);
  return `
    ${renderCollectionRail()}
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Overview</p>
          <h2>${escapeHtml(compactDateLabel(state.selectedDate))} · Pohang 21-32 ☀️</h2>
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
  const datedTasks = mockAdapter.getTasks().filter((task) => task.due);
  const selectedEvents = events.filter((event) => event.date === state.selectedDate);
  const selectedTasks = datedTasks.filter((task) => task.due === state.selectedDate);
  const eventDates = new Set([...events.map((event) => event.date), ...datedTasks.map((task) => task.due)]);
  return `
    ${renderCollectionRail()}
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Calendar</p>
          <h2>${escapeHtml(monthTitle(month))}</h2>
        </div>
        <a class="openButton" href="#/add-event">Add</a>
      </div>
      <div class="calendarGrid" aria-label="Month grid">
        ${["S", "M", "T", "W", "T", "F", "S"].map((day) => `<span class="weekday">${day}</span>`).join("")}
        ${monthCells(month)
          .map((cell) => {
            const classes = [
              "day",
              cell.muted ? "isMuted" : "",
              cell.value === ymd(new Date()) ? "isToday" : "",
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
      ${renderCalendarAgenda(selectedEvents, selectedTasks)}
    </section>
  `;
}

function renderTasks() {
  const tasks = mockAdapter.getTasks().filter((task) => taskMatchesMode(task, state.taskMode));
  return `
    ${renderCollectionRail()}
    <section class="taskFilters" aria-label="Task filters">
      <label>
        <span>Tasks</span>
        <select data-task-mode>
          <option value="active" ${state.taskMode === "active" ? "selected" : ""}>Active</option>
          <option value="done" ${state.taskMode === "done" ? "selected" : ""}>Completed</option>
        </select>
      </label>
      <label>
        <span>Order</span>
        <select data-task-sort>
          <option value="due" ${state.taskSort === "due" ? "selected" : ""}>Due</option>
          <option value="created" ${state.taskSort === "created" ? "selected" : ""}>Creation</option>
        </select>
      </label>
      <a class="openButton taskAddButton" href="#/add-task">Add</a>
    </section>
    <section class="panel">
      <div class="panelBody">${renderTaskRows(tasks)}</div>
    </section>
  `;
}

function renderAdd() {
  return state.addKind === "task" ? renderAddTask() : renderAddEvent();
}

function renderAddEvent() {
  return `
    ${renderCollectionRail()}
    <section class="panel">
      <form class="composer" data-create-event>
        <label>
          <span>Title</span>
          <input name="title" type="text" autocomplete="off" placeholder="New event" required />
        </label>
        <label class="toggleLine">
          <span>All-day</span>
          <input name="allDay" type="checkbox" data-all-day-toggle />
        </label>
        <div class="formGrid">
          <label>
            <span>Start date</span>
            <input name="startDate" type="date" value="${escapeHtml(state.selectedDate)}" required />
          </label>
          <label data-event-time-field>
            <span>Start time</span>
            <input name="startTime" type="time" value="${escapeHtml(DEFAULT_EVENT_START_TIME)}" step="300" />
          </label>
          <label>
            <span>End date</span>
            <input name="endDate" type="date" value="${escapeHtml(state.selectedDate)}" required />
          </label>
          <label data-event-time-field>
            <span>End time</span>
            <input name="endTime" type="time" value="${escapeHtml(DEFAULT_EVENT_END_TIME)}" step="300" />
          </label>
        </div>
        <label>
          <span>Repeat</span>
          <select name="repeat">
            <option value="">None</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="yearly">Yearly</option>
          </select>
        </label>
        <label data-event-time-field>
          <span>Alarm time</span>
          <input name="alarm" type="time" step="300" />
        </label>
        <label>
          <span>Memo</span>
          <textarea name="memo" rows="5" placeholder="Event notes"></textarea>
        </label>
        <button class="primaryButton" type="submit">Create local event</button>
      </form>
    </section>
  `;
}

function renderAddTask() {
  const dueEnabled = state.taskDueEnabled;
  return `
    ${renderCollectionRail()}
    <form class="taskComposer" data-create-task>
      <input name="due" type="hidden" value="${dueEnabled ? escapeHtml(state.selectedDate) : ""}" />
      <section class="panel">
        <div class="composer">
          <label>
            <span>Task</span>
            <input name="title" type="text" autocomplete="off" placeholder="New task" required />
          </label>
          <label>
            <span>Memo</span>
            <textarea name="memo" rows="6" placeholder="memo and subtasks; use -- subtask or -x done"></textarea>
          </label>
        </div>
      </section>
      ${renderAddDatePicker({ title: "Task due", allowNoDate: true })}
      <section class="panel">
        <div class="composer">
          <label>
            <span>Time</span>
            <input name="dueTime" type="time" step="300" ${dueEnabled ? "" : "disabled"} />
          </label>
          <p class="formNote">Default ${escapeHtml(DEFAULT_TASK_DUE_TIME)} when a date is used.</p>
          <label>
            <span>Priority</span>
            <select name="priority">
              <option value="">None</option>
              <option value="9">Low (!)</option>
              <option value="5">Medium (!!)</option>
              <option value="1">High (!!!)</option>
            </select>
          </label>
          <button class="primaryButton" type="submit">Create local task</button>
        </div>
      </section>
    </form>
  `;
}

function renderEditTask() {
  const taskId = hashParam("uid");
  const task = findTaskById(taskId);
  if (!task) {
    return `
      ${renderCollectionRail()}
      <section class="panel">
        <div class="panelBody">
          <p class="taskMeta">Task not found</p>
        </div>
      </section>
    `;
  }

  if (state.editingTaskId !== task.id) {
    state.editingTaskId = task.id;
    state.taskDueEnabled = Boolean(task.due);
    state.selectedDate = task.due || ymd(new Date());
  }

  const dueEnabled = state.taskDueEnabled;
  return `
    ${renderCollectionRail()}
    <form class="taskComposer" data-edit-task>
      <input name="uid" type="hidden" value="${escapeHtml(task.id)}" />
      <input name="collectionId" type="hidden" value="${escapeHtml(task.collection)}" />
      <input name="due" type="hidden" value="${dueEnabled ? escapeHtml(state.selectedDate) : ""}" />
      <section class="panel">
        <div class="composer">
          <label>
            <span>Task</span>
            <input name="title" type="text" autocomplete="off" value="${escapeHtml(task.title)}" required />
          </label>
          <label>
            <span>Memo</span>
            <textarea name="memo" rows="6" placeholder="memo and subtasks; use -- subtask or -x done">${escapeHtml(task.description)}</textarea>
          </label>
        </div>
      </section>
      ${renderAddDatePicker({ title: "Task due", allowNoDate: true })}
      <section class="panel">
        <div class="composer">
          <label>
            <span>Time</span>
            <input name="dueTime" type="time" value="${dueEnabled ? escapeHtml(task.dueTime) : ""}" step="300" ${dueEnabled ? "" : "disabled"} />
          </label>
          <p class="formNote">Default ${escapeHtml(DEFAULT_TASK_DUE_TIME)} when a date is used.</p>
          <label>
            <span>Priority</span>
            <select name="priority">
              <option value="" ${task.priority ? "" : "selected"}>None</option>
              <option value="9" ${task.priority === "9" ? "selected" : ""}>Low (!)</option>
              <option value="5" ${task.priority === "5" ? "selected" : ""}>Medium (!!)</option>
              <option value="1" ${task.priority === "1" ? "selected" : ""}>High (!!!)</option>
            </select>
          </label>
          <button class="primaryButton" type="submit">Save task</button>
        </div>
      </section>
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
  else if (route === "add") view.innerHTML = renderAdd();
  else if (route === "add-event") {
    state.addKind = "event";
    view.innerHTML = renderAddEvent();
  }
  else if (route === "add-task") {
    state.addKind = "task";
    view.innerHTML = renderAddTask();
  }
  else if (route === "edit-task") view.innerHTML = renderEditTask();
  else if (route === "services") view.innerHTML = renderServices();
  else view.innerHTML = renderToday();
}

document.addEventListener("click", (event) => {
  const day = event.target.closest("[data-date]");
  if (day) {
    state.selectedDate = day.dataset.date;
    if (getRoute() === "add-task" || getRoute() === "edit-task" || (getRoute() === "add" && state.addKind === "task")) state.taskDueEnabled = true;
    render();
    return;
  }

  const collection = event.target.closest("[data-collection]");
  if (collection) {
    state.currentCollection = collection.dataset.collection;
    render();
    return;
  }

  if (event.target.closest("[data-toggle-add-month]")) {
    state.addMonthExpanded = !state.addMonthExpanded;
    render();
    return;
  }

  if (event.target.closest("[data-clear-task-due]")) {
    state.taskDueEnabled = false;
    const form = event.target.closest("form");
    const timeInput = form?.querySelector('input[name="dueTime"]');
    if (timeInput) {
      timeInput.value = "";
      timeInput.disabled = true;
    }
    render();
    return;
  }

  if (event.target.closest("[data-use-selected-due]")) {
    state.taskDueEnabled = true;
    const form = event.target.closest("form");
    const timeInput = form?.querySelector('input[name="dueTime"]');
    if (timeInput) timeInput.disabled = false;
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

document.addEventListener("submit", async (event) => {
  const eventForm = event.target.closest("[data-create-event]");
  if (eventForm) {
    event.preventDefault();
    mockAdapter.createEvent(new FormData(eventForm));
    window.location.hash = "#/calendar";
    render();
    return;
  }

  const taskForm = event.target.closest("[data-create-task]");
  if (taskForm) {
    event.preventDefault();
    const formData = new FormData(taskForm);
    const due = taskDueFromForm(formData);
    if (taskDueHasPassed(due) && !window.confirm("This due time has already passed. Create it anyway?")) return;
    if (state.remoteCalendar.live) {
      try {
        await createRemoteTask(formData);
      } catch (error) {
        window.alert(`Could not save to Radicale: ${error.message || "unknown error"}`);
      }
      return;
    }
    mockAdapter.createTask(formData);
    window.location.hash = "#/tasks";
    render();
  }

  const editTaskForm = event.target.closest("[data-edit-task]");
  if (editTaskForm) {
    event.preventDefault();
    const formData = new FormData(editTaskForm);
    const due = taskDueFromForm(formData);
    if (taskDueHasPassed(due) && !window.confirm("This due time has already passed. Save it anyway?")) return;
    if (state.remoteCalendar.live) {
      try {
        await updateRemoteTask(formData);
      } catch (error) {
        window.alert(`Could not save to Radicale: ${error.message || "unknown error"}`);
      }
      return;
    }
    mockAdapter.updateTask(formData);
    window.location.hash = "#/tasks";
    render();
  }
});

document.addEventListener("change", (event) => {
  const taskMode = event.target.closest("[data-task-mode]");
  if (taskMode) {
    state.taskMode = taskMode.value;
    render();
    return;
  }

  const taskSort = event.target.closest("[data-task-sort]");
  if (taskSort) {
    state.taskSort = taskSort.value;
    render();
    return;
  }

  const allDayToggle = event.target.closest("[data-all-day-toggle]");
  if (!allDayToggle) return;
  const form = allDayToggle.closest("[data-create-event]");
  if (!form) return;
  form.querySelectorAll("[data-event-time-field]").forEach((field) => {
    field.classList.toggle("isDisabled", allDayToggle.checked);
    field.querySelectorAll("input").forEach((input) => {
      input.disabled = allDayToggle.checked;
    });
  });
});

window.addEventListener("hashchange", render);

if (!window.location.hash) {
  window.location.hash = "#/today";
} else {
  render();
}

loadRemoteCalendar();
