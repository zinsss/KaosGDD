const routes = {
  today: "Today",
  calendar: "Calendar",
  tasks: "Tasks",
  add: "Add",
  "add-event": "Add Event",
  "add-task": "Add Task",
  "edit-task": "Edit Task",
  services: "Services",
  rouny: "Rouny",
  memos: "Memos",
  settings: "Settings",
};

const DEFAULT_TASK_DUE_TIME = "10:00";
const DEFAULT_EVENT_START_TIME = "09:00";
const DEFAULT_EVENT_END_TIME = "10:00";
const MEMOS_URL = "https://memos.kaosgdd.net";
const ROUNY_TEMPLATE_STORAGE_KEY = "kaosgdd.v2.rouny.templates.v1";
const ROUNY_SELECTED_STORAGE_KEY = "kaosgdd.v2.rouny.selectedTemplateId.v1";
const ROUNY_INCLUDE_SATURDAY_KEY = "kaosgdd.v2.rouny.includeSaturday.v1";

const rounyDays = [
  { value: "1", label: "Mon" },
  { value: "2", label: "Tue" },
  { value: "3", label: "Wed" },
  { value: "4", label: "Thu" },
  { value: "5", label: "Fri" },
  { value: "6", label: "Sat" },
  { value: "0", label: "Sun" },
];

const rounyColors = ["pink", "peach", "yellow", "mint", "sky", "lavender", "gray"];

const navIcons = {
  today: '<path d="M4 5h16M4 12h16M4 19h10" />',
  calendar: '<path d="M8 2v4M16 2v4M3 10h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" />',
  tasks: '<path d="m9 11 3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />',
  services: '<path d="M12 3v18M3 12h18M5 5h14v14H5z" />',
  rouny: '<path d="M4 18V7l8-4 8 4v11M8 14h8M9 10h.01M15 10h.01" />',
  memos: '<path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" />',
};

const profileConfigs = {
  main: {
    label: "KaosGDD",
    defaultRoute: "today",
    nav: [
      { route: "today", label: "Today", icon: "today" },
      { route: "calendar", label: "Calendar", icon: "calendar" },
      { route: "tasks", label: "Tasks", icon: "tasks" },
      { route: "services", label: "Services", icon: "services" },
    ],
  },
  family: {
    label: "Family",
    defaultRoute: "calendar",
    nav: [
      { route: "calendar", label: "Cal", icon: "calendar" },
      { route: "tasks", label: "Tasks", icon: "tasks" },
      { route: "rouny", label: "Rouny", icon: "rouny" },
      { route: "memos", label: "Memos", icon: "memos" },
    ],
  },
};

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
    profile: "main",
    error: "",
    collections: [],
    events: [],
    tasks: [],
  },
  weatherLocation: "pohang",
  remoteWeather: {
    checked: false,
    live: false,
    key: "",
    loadingKey: "",
    error: "",
    items: [],
  },
  rouny: {
    checked: false,
    templates: [],
    selectedTemplateId: "",
    draft: null,
    page: "list",
    editingItemId: "",
    editingItemDraft: null,
    dragItemId: "",
    dragTemplateId: "",
    includeSaturday: false,
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
  weather: [
    {
      city: "pohang",
      cityName: "Pohang",
      date: ymd(new Date()),
      glyph: "☀️",
      minTemp: 21,
      maxTemp: 32,
      dayparts: [
        { label: "Morning", glyph: "🌤️", minTemp: 22, maxTemp: 27 },
        { label: "Afternoon", glyph: "☀️", minTemp: 28, maxTemp: 32 },
        { label: "Evening", glyph: "🌧️", minTemp: 25, maxTemp: 29 },
        { label: "Night", glyph: "🌙", minTemp: 21, maxTemp: 24 },
      ],
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
    return { ...state.remoteCalendar, weather: activeWeatherItems() };
  }
  return { ...mockCalendarData, weather: activeWeatherItems() };
}

function activeWeatherItems() {
  return state.remoteWeather.live ? state.remoteWeather.items : mockCalendarData.weather;
}

function collectionViews() {
  const data = activeCalendarData();
  const allIds = data.collections.map((collection) => collection.id);
  const ownerLabels = {
    zin: "GDD_ZiN",
    family: "Family",
    wife: "Wife",
  };
  const ownerSubtitles = {
    zin: "personal",
    family: "shared",
    wife: "personal",
  };
  const ownerOrder = ["family", "zin", "wife"];
  const owners = [...new Set(data.collections.map((collection) => collection.owner).filter(Boolean))].sort((a, b) => {
    const rankA = ownerOrder.includes(a) ? ownerOrder.indexOf(a) : ownerOrder.length;
    const rankB = ownerOrder.includes(b) ? ownerOrder.indexOf(b) : ownerOrder.length;
    if (rankA !== rankB) return rankA - rankB;
    return a.localeCompare(b);
  });
  const views = [
    { id: "all", name: "All", owner: "Radicale", collectionIds: allIds },
  ];
  owners.forEach((owner) => {
    const collectionIds = data.collections.filter((collection) => collection.owner === owner).map((collection) => collection.id);
    if (collectionIds.length) {
      views.push({
        id: `owner:${owner}`,
        name: ownerLabels[owner] || owner,
        owner: ownerSubtitles[owner] || owner,
        collectionIds,
      });
    }
  });
  return views;
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
  const typedTaskCollection = data.collections.find((collection) => collectionIds.includes(collection.id) && collection.components?.includes("VTODO"));
  if (typedTaskCollection) return typedTaskCollection.id;
  const taskCollectionIds = new Set(data.tasks.map((task) => task.collection));
  const taskCollection = data.collections.find((collection) => collectionIds.includes(collection.id) && taskCollectionIds.has(collection.id));
  if (taskCollection) return taskCollection.id;
  const namedTaskCollection = data.collections.find((collection) => collectionIds.includes(collection.id) && /task|reminder/i.test(collection.name));
  if (namedTaskCollection) return namedTaskCollection.id;
  return collectionIds[0] || writableCollectionId();
}

function writableEventCollectionId() {
  const data = activeCalendarData();
  const view = mockAdapter.getCurrentCollection();
  const collectionIds = view?.id !== "all" && view?.collectionIds.length
    ? view.collectionIds
    : data.collections.map((collection) => collection.id);
  const typedEventCollection = data.collections.find((collection) => collectionIds.includes(collection.id) && collection.components?.includes("VEVENT"));
  if (typedEventCollection) return typedEventCollection.id;
  const eventCollectionIds = new Set(data.events.map((event) => event.collection));
  const eventCollection = data.collections.find((collection) => collectionIds.includes(collection.id) && eventCollectionIds.has(collection.id));
  if (eventCollection) return eventCollection.id;
  const namedEventCollection = data.collections.find((collection) => collectionIds.includes(collection.id) && /calendar|event/i.test(collection.name));
  if (namedEventCollection) return namedEventCollection.id;
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
      profile: payload.profile || "main",
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
      profile: state.remoteCalendar.profile,
      error: error.message || "Calendar adapter unavailable",
    };
  }
  render();
}

function visibleMonthRange(monthValue = state.selectedDate.slice(0, 7)) {
  const cells = monthCells(monthValue);
  return { start: cells[0]?.value || state.selectedDate, end: cells[cells.length - 1]?.value || state.selectedDate };
}

async function loadRemoteWeatherForSelectedMonth() {
  const month = state.selectedDate.slice(0, 7);
  const range = visibleMonthRange(month);
  const key = `${state.weatherLocation}:${range.start}:${range.end}`;
  if (state.remoteWeather.key === key || state.remoteWeather.loadingKey === key) return;
  state.remoteWeather.loadingKey = key;
  try {
    const params = new URLSearchParams({
      city: state.weatherLocation,
      start: range.start,
      end: range.end,
    });
    const response = await fetch(`/api/weather/month?${params.toString()}`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.remoteWeather = {
      checked: true,
      live: Boolean(payload.ok && Array.isArray(payload.items)),
      key,
      loadingKey: "",
      error: payload.error || "",
      items: normalizeWeatherItems(payload.items || []),
    };
  } catch (error) {
    state.remoteWeather = {
      ...state.remoteWeather,
      checked: true,
      live: false,
      key,
      loadingKey: "",
      error: error.message || "Weather unavailable",
    };
  }
  if (getRoute() === "calendar" || getRoute() === "today") render();
}

function normalizeWeatherItems(items) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => ({
      city: String(item?.city || ""),
      cityName: String(item?.cityName || item?.city || ""),
      date: String(item?.date || ""),
      glyph: String(item?.glyph || ""),
      condition: String(item?.condition || ""),
      minTemp: item?.minTemp ?? "",
      maxTemp: item?.maxTemp ?? "",
      source: String(item?.source || ""),
      dayparts: Array.isArray(item?.dayparts)
        ? item.dayparts.map((part) => ({
            label: String(part?.label || ""),
            glyph: String(part?.glyph || ""),
            condition: String(part?.condition || ""),
            minTemp: part?.minTemp ?? "",
            maxTemp: part?.maxTemp ?? "",
          }))
        : [],
    }))
    .filter((item) => item.date);
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

async function createRemoteEvent(formData) {
  const response = await fetch("/api/calendar/events", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      collectionId: writableEventCollectionId(),
      title: String(formData.get("title") || "").trim(),
      allDay: formData.get("allDay") === "on",
      startDate: String(formData.get("startDate") || state.selectedDate),
      startTime: String(formData.get("startTime") || DEFAULT_EVENT_START_TIME),
      endDate: String(formData.get("endDate") || formData.get("startDate") || state.selectedDate),
      endTime: String(formData.get("endTime") || DEFAULT_EVENT_END_TIME),
      repeat: String(formData.get("repeat") || ""),
      alarmTime: String(formData.get("alarm") || ""),
      memo: String(formData.get("memo") || "").trim(),
    }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  state.selectedDate = String(formData.get("startDate") || state.selectedDate);
  window.location.hash = "#/calendar";
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
  const date = rawDue || (rawTime ? ymd(new Date()) : "");
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
  if (!routes[route]) return profileConfig().defaultRoute;
  if (portalProfile() === "family" && (route === "today" || route === "services")) return profileConfig().defaultRoute;
  if (portalProfile() === "main" && (route === "rouny" || route === "memos")) return profileConfig().defaultRoute;
  return route;
}

function portalProfile() {
  return window.location.hostname === "family.kaosgdd.net" ? "family" : "main";
}

function profileConfig() {
  return profileConfigs[portalProfile()];
}

function activeNavRoute(route) {
  if (route === "add" || route === "add-event") return "calendar";
  if (route === "add-task" || route === "edit-task") return "tasks";
  return route;
}

function renderBottomNav(route) {
  const nav = document.getElementById("bottomNav");
  if (!nav) return;
  const activeRoute = activeNavRoute(route);
  nav.innerHTML = profileConfig()
    .nav.map(
      (item) => `
        <a href="#/${item.route}" data-nav="${item.route}" class="${item.route === activeRoute ? "isActive" : ""}" aria-label="${escapeHtml(item.label)}">
          <svg aria-hidden="true" viewBox="0 0 24 24">${navIcons[item.icon]}</svg>
          <span>${escapeHtml(item.label)}</span>
        </a>
      `,
    )
    .join("");
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

function shiftSelectedMonth(offset) {
  const [year, month, day] = state.selectedDate.split("-").map(Number);
  const target = new Date(year, month - 1 + offset, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(day, lastDay));
  state.selectedDate = ymd(target);
}

function selectToday() {
  state.selectedDate = ymd(new Date());
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
  document.querySelector(".kicker").textContent = profileConfig().label;
  const app = document.querySelector(".app");
  app.dataset.route = route;
  app.dataset.profile = portalProfile();
  document.querySelector(".settingsButton")?.classList.toggle("isActive", route === "settings");
  renderBottomNav(route);
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
  const weather = weatherForDate(state.selectedDate);
  if (!events.length && !tasks.length && !weather) return `<div class="panelBody"><p class="taskMeta">No items</p></div>`;
  return `
    ${weather ? renderSelectedWeather(weather) : ""}
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

function weatherForDate(dateValue) {
  return activeCalendarData().weather?.find((weather) => weather.date === dateValue) || null;
}

function countByDate(items, dateKey) {
  return items.reduce((counts, item) => {
    const value = item[dateKey];
    if (value) counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});
}

function hasDutyEvent(event) {
  const title = String(event.title || event.summary || "").trim();
  const detail = String(event.detail || event.description || "").trim();
  const categories = Array.isArray(event.categories) ? event.categories : [];
  return title === "당직" || detail === "당직" || categories.some((category) => String(category).trim() === "당직");
}

function dateTone(dateValue) {
  const date = new Date(`${dateValue}T00:00:00`);
  const day = date.getDay();
  if (day === 0) return "isSunday";
  if (day === 6) return "isSaturday";
  return "";
}

function tempRange(item) {
  if (!item || item.minTemp === undefined || item.maxTemp === undefined || item.minTemp === "" || item.maxTemp === "") return "";
  return `${item.minTemp}-${item.maxTemp}`;
}

function weatherGlyph(weather) {
  const raw = String(weather?.glyph || weather?.condition || "").toLowerCase();
  const condition = String(weather?.condition || "").toLowerCase();
  const value = `${raw} ${condition}`;
  if (value.includes("thunder") || value.includes("storm") || value.includes("⛈")) return "\ue31d";
  if (value.includes("snow") || value.includes("sleet") || value.includes("❄")) return "\ue31a";
  if (value.includes("rain") || value.includes("shower") || value.includes("drizzle") || value.includes("🌧") || value.includes("☔")) return "\ue318";
  if (value.includes("cloud") || value.includes("overcast") || value.includes("☁")) return "\ue312";
  if (value.includes("part") || value.includes("few") || value.includes("🌤") || value.includes("⛅")) return "\ue302";
  if (value.includes("night") || value.includes("moon") || value.includes("🌙")) return "\ue32b";
  if (value.includes("fog") || value.includes("mist") || value.includes("haze")) return "\ue313";
  if (value.includes("sun") || value.includes("clear") || value.includes("☀")) return "\ue30d";
  return raw ? "\ue371" : "";
}

function isPastDate(dateValue) {
  return String(dateValue || "") < ymd(new Date());
}

function renderSelectedWeather(weather) {
  const dayparts = weather.dayparts || [];
  if (isPastDate(weather.date) || !dayparts.length) {
    return `
      <div class="selectedWeatherCompact" aria-label="Selected day weather">
        <span>Weather</span>
        <strong>${escapeHtml(weatherGlyph(weather))}</strong>
        <em>${escapeHtml(tempRange(weather))}</em>
      </div>
    `;
  }
  return `
    <div class="selectedWeather" aria-label="Selected day weather">
      <div class="selectedWeatherSummary">
        <span class="selectedWeatherGlyph">${escapeHtml(weatherGlyph(weather))}</span>
        <span class="selectedWeatherRange">${escapeHtml(tempRange(weather))}</span>
      </div>
      <div class="selectedWeatherParts">
        ${["Morning", "Afternoon", "Evening", "Night"]
          .map((label) => {
            const part = dayparts.find((item) => item.label === label) || {};
            return `
              <div class="weatherPart">
                <span class="weatherPartLabel">${escapeHtml(label)}</span>
                <span class="weatherPartValue">${escapeHtml([weatherGlyph(part), tempRange(part)].filter(Boolean).join(" "))}</span>
              </div>
            `;
          })
          .join("")}
      </div>
    </div>
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
  const eventCounts = countByDate(events, "date");
  const taskCounts = countByDate(datedTasks, "due");
  const dutyDates = new Set(events.filter(hasDutyEvent).map((event) => event.date));
  const weatherByDate = new Map((activeCalendarData().weather || []).map((weather) => [weather.date, weather]));
  return `
    ${renderCollectionRail()}
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Calendar</p>
          <h2>${escapeHtml(monthTitle(month))}</h2>
        </div>
        <div class="calendarHeaderActions" aria-label="Calendar actions">
          <div class="monthNav" aria-label="Month navigation">
            <button class="monthNavButton" type="button" data-month-shift="-1" aria-label="Previous month">&lt;&lt;</button>
            <button class="monthTodayButton" type="button" data-month-today>Today</button>
            <button class="monthNavButton" type="button" data-month-shift="1" aria-label="Next month">&gt;&gt;</button>
          </div>
          <a class="openButton" href="#/add-event">Add</a>
        </div>
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
              dateTone(cell.value),
            ]
              .filter(Boolean)
              .join(" ");
            const weather = weatherByDate.get(cell.value);
            const eventCount = eventCounts[cell.value] || 0;
            const taskCount = taskCounts[cell.value] || 0;
            const hasDuty = dutyDates.has(cell.value);
            return `
              <button class="${classes}" type="button" data-date="${cell.value}">
                <span class="dayHeader">
                  <span class="dayNumber">${cell.label}</span>
                  ${hasDuty ? `<span class="dayDutyMarker" aria-label="당직">•</span>` : ""}
                </span>
                ${weatherGlyph(weather) ? `<span class="dayWeatherGlyph">${escapeHtml(weatherGlyph(weather))}</span>` : ""}
                ${
                  eventCount || taskCount
                    ? `
                      <span class="dayMarkers">
                        ${eventCount ? `<span class="dayEventCount">${eventCount}</span>` : ""}
                        ${taskCount ? `<span class="dayTaskCount">${taskCount}</span>` : ""}
                      </span>
                    `
                    : ""
                }
              </button>
            `;
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
        <button class="primaryButton" type="submit">Create event</button>
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
            <input name="dueTime" type="time" step="300" />
          </label>
          <p class="formNote">Default ${escapeHtml(DEFAULT_TASK_DUE_TIME)} when a date is used. Time without date uses today.</p>
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
            <input name="dueTime" type="time" value="${dueEnabled ? escapeHtml(task.dueTime) : ""}" step="300" />
          </label>
          <p class="formNote">Default ${escapeHtml(DEFAULT_TASK_DUE_TIME)} when a date is used. Time without date uses today.</p>
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

function createId(prefix = "id") {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function cloneValue(value) {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function defaultRounyItem() {
  return {
    id: createId("rouny-item"),
    title: "",
    dayOfWeek: String(new Date().getDay()),
    startTime: "09:00",
    endTime: "09:40",
    memo: "",
    color: "pink",
  };
}

function defaultRounyTemplate(name = "New template") {
  const now = new Date().toISOString();
  return {
    id: createId("rouny-template"),
    name,
    items: [defaultRounyItem()],
    createdAt: now,
    updatedAt: now,
  };
}

function normalizeRounyItem(item) {
  if (!item || typeof item !== "object") return null;
  return {
    id: String(item.id || createId("rouny-item")),
    title: String(item.title || ""),
    dayOfWeek: rounyDays.some((day) => day.value === String(item.dayOfWeek)) ? String(item.dayOfWeek) : "1",
    startTime: String(item.startTime || "09:00"),
    endTime: String(item.endTime || "09:40"),
    memo: String(item.memo || ""),
    color: rounyColors.includes(item.color) ? item.color : "pink",
  };
}

function normalizeRounyTemplate(template) {
  if (!template || typeof template !== "object") return null;
  const now = new Date().toISOString();
  const items = Array.isArray(template.items) ? template.items.map(normalizeRounyItem).filter(Boolean) : [];
  return {
    id: String(template.id || createId("rouny-template")),
    name: String(template.name || "Untitled template").trim() || "Untitled template",
    items: items.length ? items : [defaultRounyItem()],
    createdAt: String(template.createdAt || now),
    updatedAt: String(template.updatedAt || template.createdAt || now),
  };
}

function loadRounyTemplates() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(ROUNY_TEMPLATE_STORAGE_KEY) || "[]");
    const templates = Array.isArray(parsed) ? parsed.map(normalizeRounyTemplate).filter(Boolean) : [];
    return templates.length ? templates : [defaultRounyTemplate("Basic")];
  } catch {
    return [defaultRounyTemplate("Basic")];
  }
}

function saveRounyTemplates(templates) {
  const normalized = templates.map(normalizeRounyTemplate).filter(Boolean);
  state.rouny.templates = normalized;
  window.localStorage.setItem(ROUNY_TEMPLATE_STORAGE_KEY, JSON.stringify(normalized));
  if (state.rouny.selectedTemplateId) window.localStorage.setItem(ROUNY_SELECTED_STORAGE_KEY, state.rouny.selectedTemplateId);
}

function ensureRounyState() {
  if (!state.rouny.checked) {
    state.rouny.templates = loadRounyTemplates();
    state.rouny.selectedTemplateId = window.localStorage.getItem(ROUNY_SELECTED_STORAGE_KEY) || state.rouny.templates[0]?.id || "";
    state.rouny.includeSaturday = window.localStorage.getItem(ROUNY_INCLUDE_SATURDAY_KEY) === "true";
    if (!state.rouny.templates.some((template) => template.id === state.rouny.selectedTemplateId)) {
      state.rouny.selectedTemplateId = state.rouny.templates[0]?.id || "";
    }
    state.rouny.checked = true;
  }
  if (!state.rouny.draft) {
    const selected = state.rouny.templates.find((template) => template.id === state.rouny.selectedTemplateId) || state.rouny.templates[0];
    state.rouny.draft = cloneValue(selected || defaultRounyTemplate("Basic"));
    state.rouny.selectedTemplateId = state.rouny.draft.id;
  }
}

function collectRounyDraft() {
  const form = document.querySelector("[data-rouny-editor]");
  if (!form || !state.rouny.draft) return state.rouny.draft;
  state.rouny.draft = normalizeRounyTemplate({
    ...state.rouny.draft,
    name: form.querySelector('[name="templateName"]')?.value || "",
  });
  return state.rouny.draft;
}

function selectRounyTemplate(templateId) {
  const template = state.rouny.templates.find((item) => item.id === templateId);
  if (!template) return;
  state.rouny.selectedTemplateId = template.id;
  state.rouny.draft = cloneValue(template);
  state.rouny.page = "detail";
  state.rouny.editingItemId = "";
  state.rouny.editingItemDraft = null;
  window.localStorage.setItem(ROUNY_SELECTED_STORAGE_KEY, template.id);
}

function saveRounyDraft({ asCopy = false } = {}) {
  const draft = collectRounyDraft();
  if (!draft?.name.trim()) {
    window.alert("Template name is required.");
    return;
  }
  const now = new Date().toISOString();
  const nextDraft = normalizeRounyTemplate({
    ...draft,
    id: asCopy ? createId("rouny-template") : draft.id,
    name: asCopy ? `${draft.name} copy` : draft.name,
    createdAt: asCopy ? now : draft.createdAt,
    updatedAt: now,
  });
  const exists = !asCopy && state.rouny.templates.some((template) => template.id === nextDraft.id);
  const templates = exists
    ? state.rouny.templates.map((template) => (template.id === nextDraft.id ? nextDraft : template))
    : [...state.rouny.templates, nextDraft];
  state.rouny.selectedTemplateId = nextDraft.id;
  state.rouny.draft = cloneValue(nextDraft);
  saveRounyTemplates(templates);
}

function deleteRounyTemplate(templateId) {
  if (state.rouny.templates.length <= 1) {
    window.alert("Keep at least one template.");
    return;
  }
  if (!window.confirm("Delete this template?")) return;
  const templates = state.rouny.templates.filter((template) => template.id !== templateId);
  state.rouny.selectedTemplateId = templates[0]?.id || "";
  state.rouny.draft = cloneValue(templates[0] || defaultRounyTemplate("Basic"));
  state.rouny.page = "list";
  state.rouny.editingItemId = "";
  state.rouny.editingItemDraft = null;
  saveRounyTemplates(templates);
}

function reorderRounyTemplates(sourceId, targetId) {
  if (!sourceId || !targetId || sourceId === targetId) return;
  const templates = [...state.rouny.templates];
  const from = templates.findIndex((template) => template.id === sourceId);
  const to = templates.findIndex((template) => template.id === targetId);
  if (from < 0 || to < 0) return;
  const [moved] = templates.splice(from, 1);
  templates.splice(to, 0, moved);
  saveRounyTemplates(templates);
}

function rounyMinutes(timeValue) {
  const match = String(timeValue || "").match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return 0;
  return Number(match[1]) * 60 + Number(match[2]);
}

function sortRounyItems(items) {
  return [...items].sort((a, b) => Number(a.dayOfWeek) - Number(b.dayOfWeek) || rounyMinutes(a.startTime) - rounyMinutes(b.startTime));
}

function updateRounyDraftItem(itemId, patch) {
  ensureRounyState();
  state.rouny.draft.items = state.rouny.draft.items.map((item) =>
    item.id === itemId ? normalizeRounyItem({ ...item, ...patch }) : item,
  );
}

function moveRounyDraftItem(itemId, dayOfWeek, targetItemId = "") {
  const moving = state.rouny.draft?.items.find((item) => item.id === itemId);
  if (!moving || !rounyDays.some((day) => day.value === String(dayOfWeek))) return;
  const target = state.rouny.draft.items.find((item) => item.id === targetItemId);
  updateRounyDraftItem(itemId, {
    dayOfWeek: String(dayOfWeek),
    ...(target ? { startTime: target.startTime, endTime: target.endTime } : {}),
  });
}

function rounyTimeLabel(item) {
  return `${String(item.startTime || "").slice(0, 5)}-${String(item.endTime || "").slice(0, 5)}`;
}

function rounyColorClass(color) {
  return rounyColors.includes(color) ? `is${color[0].toUpperCase()}${color.slice(1)}` : "isPink";
}

function rounyGridDays() {
  return rounyDays.filter((day) => Number(day.value) >= 1 && Number(day.value) <= (state.rouny.includeSaturday ? 6 : 5));
}

function renderRounyGrid(template) {
  const grouped = rounyDays.reduce((days, day) => ({ ...days, [day.value]: [] }), {});
  const visibleDays = rounyGridDays();
  sortRounyItems(template.items).forEach((item) => {
    grouped[item.dayOfWeek]?.push(item);
  });
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Week</p>
          <h2>${escapeHtml(template.name)}</h2>
        </div>
        <label class="rounyGridToggle">
          <input type="checkbox" data-rouny-saturday ${state.rouny.includeSaturday ? "checked" : ""} />
          <span>Sat</span>
        </label>
      </div>
      <div class="rounyWeekGrid ${state.rouny.includeSaturday ? "hasSaturday" : "isWeekdays"}" aria-label="Rouny weekly timetable">
        ${visibleDays
          .map(
            (day) => `
              <section class="rounyDayColumn" data-rouny-day="${escapeHtml(day.value)}">
                <h3>${escapeHtml(day.label)}</h3>
                <div class="rounyDayItems">
                  ${
                    grouped[day.value].length
                      ? grouped[day.value]
                          .map(
                            (item) => `
                              <article class="rounyBlock ${rounyColorClass(item.color)}" draggable="true" data-rouny-grid-item="${escapeHtml(item.id)}" data-rouny-day="${escapeHtml(day.value)}">
                                <strong>${escapeHtml(item.title || "Untitled")}</strong>
                                <span>${escapeHtml(rounyTimeLabel(item))}</span>
                                ${item.memo ? `<em>${escapeHtml(item.memo)}</em>` : ""}
                              </article>
                            `,
                          )
                          .join("")
                      : `<p>No items</p>`
                  }
                </div>
              </section>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderRouny() {
  ensureRounyState();
  if (state.rouny.page !== "detail") return renderRounyTemplateList();
  return renderRounyTemplateDetail();
}

function renderRounyTemplateList() {
  ensureRounyState();
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Rouny</p>
          <h2>Templates</h2>
        </div>
        <button class="openButton" type="button" data-rouny-new>New</button>
      </div>
      <div class="panelBody">
        <div class="rounyTemplateList" aria-label="Saved Rouny templates">
          ${state.rouny.templates
            .map(
              (template) => `
                <div class="rounyTemplateRow ${template.id === state.rouny.selectedTemplateId ? "isActive" : ""}" draggable="true" data-rouny-template-id="${escapeHtml(template.id)}">
                  <button class="rounyDragHandle" type="button" aria-label="Drag template">≡</button>
                  <button class="rounyTemplateButton" type="button" data-rouny-select="${escapeHtml(template.id)}">
                    <strong>${escapeHtml(template.name)}</strong>
                    <span>${template.items.length} class${template.items.length === 1 ? "" : "es"}</span>
                  </button>
                  <button class="plainButton" type="button" data-rouny-delete="${escapeHtml(template.id)}">Delete</button>
                </div>
              `,
            )
            .join("")}
        </div>
      </div>
    </section>
  `;
}

function renderRounyTemplateDetail() {
  const draft = state.rouny.draft;
  const editingItem = state.rouny.editingItemId
    ? draft.items.find((item) => item.id === state.rouny.editingItemId) || state.rouny.editingItemDraft
    : null;
  return `
    <form class="rounyEditor" data-rouny-editor>
      <section class="panel">
        <div class="panelHeader">
          <div>
            <p class="label">Rouny</p>
            <h2>${escapeHtml(draft.name)}</h2>
          </div>
          <button class="openButton" type="button" data-rouny-back>List</button>
        </div>
        <div class="composer">
          <label>
            <span>Template name</span>
            <input name="templateName" type="text" autocomplete="off" value="${escapeHtml(draft.name)}" />
          </label>
        </div>
      </section>
      ${renderRounyGrid(draft)}
      <section class="rounyActions">
        <button class="openButton" type="button" data-rouny-add-item>Add class</button>
        <button class="primaryButton" type="button" data-rouny-save>Save</button>
        <button class="openButton" type="button" data-rouny-save-as>Save as</button>
      </section>
    </form>
    ${editingItem ? renderRounyClassLayer(editingItem, !draft.items.some((item) => item.id === editingItem.id)) : ""}
  `;
}

function renderRounyClassLayer(item, isNew = false) {
  return `
    <div class="rounyLayerBackdrop" data-rouny-close-layer></div>
    <aside class="rounyLayer" aria-label="${isNew ? "Add class" : "Edit class"}">
      <div class="panelHeader">
        <div>
          <p class="label">Rouny</p>
          <h2>${isNew ? "Add class" : "Edit class"}</h2>
        </div>
        <button class="iconTextButton" type="button" data-rouny-close-layer aria-label="Close">×</button>
      </div>
      <form class="rounyLayerForm" data-rouny-class-form data-rouny-item-id="${escapeHtml(item.id)}">
        ${renderRounyItem(item)}
        <div class="rounyActions">
          ${isNew ? "" : `<button class="plainButton" type="button" data-rouny-remove-item="${escapeHtml(item.id)}">Delete</button>`}
          <button class="primaryButton" type="submit">Done</button>
        </div>
      </form>
    </aside>
  `;
}

function renderRounyItem(item) {
  return `
    <div class="rounyItem" data-rouny-item-id="${escapeHtml(item.id)}">
      <div class="rounyItemGrid">
        <label>
          <span>Title</span>
          <input name="title" type="text" autocomplete="off" value="${escapeHtml(item.title)}" placeholder="Activity" />
        </label>
        <label>
          <span>Day</span>
          <select name="dayOfWeek">
            ${rounyDays.map((day) => `<option value="${day.value}" ${item.dayOfWeek === day.value ? "selected" : ""}>${day.label}</option>`).join("")}
          </select>
        </label>
        <label>
          <span>Start</span>
          <input name="startTime" type="time" step="600" value="${escapeHtml(item.startTime)}" />
        </label>
        <label>
          <span>End</span>
          <input name="endTime" type="time" step="600" value="${escapeHtml(item.endTime)}" />
        </label>
        <label>
          <span>Color</span>
          <select name="color">
            ${rounyColors.map((color) => `<option value="${color}" ${item.color === color ? "selected" : ""}>${color}</option>`).join("")}
          </select>
        </label>
        <button class="iconTextButton" type="button" data-rouny-remove-item="${escapeHtml(item.id)}" aria-label="Remove item">×</button>
      </div>
      <label class="rounyMemo">
        <span>Memo</span>
        <input name="memo" type="text" autocomplete="off" value="${escapeHtml(item.memo)}" placeholder="Optional" />
      </label>
    </div>
  `;
}

function renderMemos() {
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">Memos</p>
          <h2>Notes</h2>
        </div>
        <a class="openButton" href="${escapeHtml(MEMOS_URL)}">Open</a>
      </div>
      <div class="panelBody">
        <p class="taskMeta">Memos opens as its own service with its own login.</p>
      </div>
    </section>
  `;
}

function renderSettings() {
  const config = profileConfig();
  const items =
    portalProfile() === "family"
      ? [
          ["Portal", "Family"],
          ["Calendar", "Wife + Family shared"],
          ["Tasks", "Wife + Family shared"],
          ["Theme", "Pastel family"],
        ]
      : [
          ["Portal", "KaosGDD"],
          ["Calendar", "ZiN + Family shared"],
          ["Tasks", "ZiN + Family shared"],
          ["Weather", "Pohang, Daegu, Yeongdeok"],
        ];
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <p class="label">${escapeHtml(config.label)}</p>
          <h2>Settings</h2>
        </div>
      </div>
      <div class="panelBody">
        <dl class="settingsList">
          ${items
            .map(
              ([label, value]) => `
                <div>
                  <dt>${escapeHtml(label)}</dt>
                  <dd>${escapeHtml(value)}</dd>
                </div>
              `,
            )
            .join("")}
        </dl>
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
  else if (route === "rouny") view.innerHTML = renderRouny();
  else if (route === "memos") view.innerHTML = renderMemos();
  else if (route === "settings") view.innerHTML = renderSettings();
  else view.innerHTML = renderToday();
  if (route === "calendar" || route === "today") {
    loadRemoteWeatherForSelectedMonth();
  }
}

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-rouny-new]")) {
    collectRounyDraft();
    state.rouny.draft = defaultRounyTemplate("New template");
    state.rouny.selectedTemplateId = state.rouny.draft.id;
    state.rouny.page = "detail";
    state.rouny.editingItemId = "";
    state.rouny.editingItemDraft = null;
    render();
    return;
  }

  if (event.target.closest("[data-rouny-back]")) {
    collectRounyDraft();
    state.rouny.page = "list";
    state.rouny.editingItemId = "";
    state.rouny.editingItemDraft = null;
    render();
    return;
  }

  const rounySelect = event.target.closest("[data-rouny-select]");
  if (rounySelect) {
    selectRounyTemplate(rounySelect.dataset.rounySelect);
    render();
    return;
  }

  const rounyDelete = event.target.closest("[data-rouny-delete]");
  if (rounyDelete) {
    deleteRounyTemplate(rounyDelete.dataset.rounyDelete);
    render();
    return;
  }

  if (event.target.closest("[data-rouny-add-item]")) {
    collectRounyDraft();
    const item = defaultRounyItem();
    state.rouny.editingItemId = item.id;
    state.rouny.editingItemDraft = item;
    render();
    return;
  }

  const rounyGridItem = event.target.closest("[data-rouny-grid-item]");
  if (rounyGridItem) {
    state.rouny.editingItemId = rounyGridItem.dataset.rounyGridItem;
    state.rouny.editingItemDraft = null;
    render();
    return;
  }

  if (event.target.closest("[data-rouny-close-layer]")) {
    state.rouny.editingItemId = "";
    state.rouny.editingItemDraft = null;
    render();
    return;
  }

  const rounyRemoveItem = event.target.closest("[data-rouny-remove-item]");
  if (rounyRemoveItem) {
    collectRounyDraft();
    if (state.rouny.draft.items.length <= 1) {
      state.rouny.draft.items = [defaultRounyItem()];
    } else {
      state.rouny.draft.items = state.rouny.draft.items.filter((item) => item.id !== rounyRemoveItem.dataset.rounyRemoveItem);
    }
    state.rouny.editingItemId = "";
    state.rouny.editingItemDraft = null;
    render();
    return;
  }

  if (event.target.closest("[data-rouny-save]")) {
    saveRounyDraft();
    render();
    return;
  }

  if (event.target.closest("[data-rouny-save-as]")) {
    saveRounyDraft({ asCopy: true });
    render();
    return;
  }

  const day = event.target.closest("[data-date]");
  if (day) {
    const previousMonth = state.selectedDate.slice(0, 7);
    state.selectedDate = day.dataset.date;
    if (getRoute() === "add-task" || getRoute() === "edit-task" || (getRoute() === "add" && state.addKind === "task")) state.taskDueEnabled = true;
    render();
    if (state.selectedDate.slice(0, 7) !== previousMonth) loadRemoteWeatherForSelectedMonth();
    return;
  }

  const collection = event.target.closest("[data-collection]");
  if (collection) {
    state.currentCollection = collection.dataset.collection;
    render();
    return;
  }

  const monthShift = event.target.closest("[data-month-shift]");
  if (monthShift) {
    const previousMonth = state.selectedDate.slice(0, 7);
    shiftSelectedMonth(Number(monthShift.dataset.monthShift));
    render();
    if (state.selectedDate.slice(0, 7) !== previousMonth) loadRemoteWeatherForSelectedMonth();
    return;
  }

  if (event.target.closest("[data-month-today]")) {
    const previousMonth = state.selectedDate.slice(0, 7);
    selectToday();
    render();
    if (state.selectedDate.slice(0, 7) !== previousMonth) loadRemoteWeatherForSelectedMonth();
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
    }
    render();
    return;
  }

  if (event.target.closest("[data-use-selected-due]")) {
    state.taskDueEnabled = true;
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
  const rounyClassForm = event.target.closest("[data-rouny-class-form]");
  if (rounyClassForm) {
    event.preventDefault();
    const itemId = rounyClassForm.dataset.rounyItemId || createId("rouny-item");
    const item = normalizeRounyItem({
      id: itemId,
      title: rounyClassForm.querySelector('[name="title"]')?.value || "",
      dayOfWeek: rounyClassForm.querySelector('[name="dayOfWeek"]')?.value || "1",
      startTime: rounyClassForm.querySelector('[name="startTime"]')?.value || "09:00",
      endTime: rounyClassForm.querySelector('[name="endTime"]')?.value || "09:40",
      memo: rounyClassForm.querySelector('[name="memo"]')?.value || "",
      color: rounyClassForm.querySelector('[name="color"]')?.value || "pink",
    });
    const exists = state.rouny.draft.items.some((draftItem) => draftItem.id === itemId);
    state.rouny.draft.items = exists
      ? state.rouny.draft.items.map((draftItem) => (draftItem.id === itemId ? item : draftItem))
      : [...state.rouny.draft.items, item];
    state.rouny.editingItemId = "";
    state.rouny.editingItemDraft = null;
    render();
    return;
  }

  if (event.target.closest("[data-rouny-editor]")) {
    event.preventDefault();
    saveRounyDraft();
    render();
    return;
  }

  const eventForm = event.target.closest("[data-create-event]");
  if (eventForm) {
    event.preventDefault();
    const formData = new FormData(eventForm);
    if (state.remoteCalendar.live) {
      try {
        await createRemoteEvent(formData);
      } catch (error) {
        window.alert(`Could not save to Radicale: ${error.message || "unknown error"}`);
      }
      return;
    }
    mockAdapter.createEvent(formData);
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

document.addEventListener("dragstart", (event) => {
  const item = event.target.closest("[data-rouny-grid-item]");
  if (item) {
    state.rouny.dragItemId = item.dataset.rounyGridItem;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", state.rouny.dragItemId);
    return;
  }

  const row = event.target.closest("[data-rouny-template-id]");
  if (!row) return;
  state.rouny.dragTemplateId = row.dataset.rounyTemplateId;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", state.rouny.dragTemplateId);
});

document.addEventListener("dragover", (event) => {
  const day = event.target.closest("[data-rouny-day]");
  if (day && state.rouny.dragItemId) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    return;
  }

  const row = event.target.closest("[data-rouny-template-id]");
  if (!row || !state.rouny.dragTemplateId) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
});

document.addEventListener("drop", (event) => {
  const day = event.target.closest("[data-rouny-day]");
  if (day && state.rouny.dragItemId) {
    event.preventDefault();
    const targetItem = event.target.closest("[data-rouny-grid-item]");
    moveRounyDraftItem(state.rouny.dragItemId, day.dataset.rounyDay, targetItem?.dataset.rounyGridItem || "");
    state.rouny.editingItemId = state.rouny.dragItemId;
    state.rouny.editingItemDraft = null;
    state.rouny.dragItemId = "";
    render();
    return;
  }

  const row = event.target.closest("[data-rouny-template-id]");
  if (!row || !state.rouny.dragTemplateId) return;
  event.preventDefault();
  reorderRounyTemplates(state.rouny.dragTemplateId, row.dataset.rounyTemplateId);
  state.rouny.dragTemplateId = "";
  render();
});

document.addEventListener("dragend", () => {
  state.rouny.dragTemplateId = "";
  state.rouny.dragItemId = "";
});

document.addEventListener("change", (event) => {
  const rounySaturday = event.target.closest("[data-rouny-saturday]");
  if (rounySaturday) {
    state.rouny.includeSaturday = rounySaturday.checked;
    window.localStorage.setItem(ROUNY_INCLUDE_SATURDAY_KEY, String(state.rouny.includeSaturday));
    render();
    return;
  }

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
  window.location.hash = `#/${profileConfig().defaultRoute}`;
} else {
  render();
}

loadRemoteCalendar();
