/* A 401 anywhere means the session ended: the app shows the sign-in page again. */
function checkAuth(res) {
  if (res.status === 401) window.dispatchEvent(new Event("auth-required"));
}

async function getJSON(url) {
  const res = await fetch(url);
  checkAuth(res);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Erreur HTTP ${res.status}`);
  }
  return res.json();
}

function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "" && v !== false) search.append(k, v);
  });
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const api = {
  me: () => getJSON("/api/me"),
  logout: () => fetch("/auth/logout", { method: "POST" }),
  dashboard: () => getJSON("/api/dashboard"),
  project: (id) => getJSON(`/api/projects/${id}`),
  records: (entityType, params = {}) => getJSON(`/api/records/${entityType}${qs(params)}`),
  people: () => getJSON("/api/people"),
  person: (id) => getJSON(`/api/people/${id}`),
  search: (q) => getJSON(`/api/search${qs({ q, limit: 12 })}`),
  statuses: () => getJSON("/api/statuses"),
  entityTypes: () => getJSON("/api/entity-types"),
  models: () => getJSON("/api/models").catch(() => ({ models: [], default: "" })),
  syncStatus: () => getJSON("/api/sync/status"),
  syncRuns: () => getJSON("/api/sync/runs"),
  syncAudit: (includeUnsynced) => getJSON(`/api/sync/audit${qs({ include_unsynced: includeUnsynced })}`),
  async startSync(mode = "auto") {
    const res = await fetch(`/api/sync${qs({ mode })}`, { method: "POST" });
    checkAuth(res);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Erreur HTTP ${res.status}`);
    }
    return res.json();
  },
};

/* Thumbnails: requests made within the same tick are batched into one call per type. */
const thumbQueues = new Map();
export function fetchThumbnail(entityType, id) {
  return new Promise((resolve) => {
    let queue = thumbQueues.get(entityType);
    if (!queue) {
      queue = new Map();
      thumbQueues.set(entityType, queue);
      setTimeout(async () => {
        thumbQueues.delete(entityType);
        const ids = [...queue.keys()];
        let urls = {};
        try {
          urls = await getJSON(`/api/thumbnails${qs({ entity_type: entityType, ids: ids.join(",") })}`);
        } catch {
          /* thumbnails are optional */
        }
        queue.forEach((resolvers, key) => resolvers.forEach((r) => r(urls[key] || null)));
      }, 40);
    }
    if (!queue.has(String(id))) queue.set(String(id), []);
    queue.get(String(id)).push(resolve);
  });
}

export function streamChat({ question, history, model, onSources, onToken, onError, onDone }) {
  const controller = new AbortController();
  fetch("/api/query/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history, model }),
    signal: controller.signal,
  })
    .then(async (response) => {
      checkAuth(response);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `Erreur HTTP ${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop();
        for (const evt of events) {
          if (!evt.startsWith("data: ")) continue;
          let event;
          try {
            event = JSON.parse(evt.slice(6));
          } catch {
            continue;
          }
          if (event.type === "sources") onSources?.(event.sources);
          else if (event.type === "token") onToken?.(event.token);
          else if (event.type === "error") onError?.(new Error(event.error));
        }
      }
      onDone?.();
    })
    .catch((err) => {
      if (err.name !== "AbortError") onError?.(err);
      onDone?.();
    });
  return controller;
}
