import { useCallback, useEffect, useRef, useState } from "react";

/* ---------- hash router: #/projects/12/tasks?step=3 ---------- */
function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  return { path, parts: path.split("/").filter(Boolean), query: Object.fromEntries(new URLSearchParams(query)) };
}

export function useRoute() {
  const [route, setRoute] = useState(parseHash);
  useEffect(() => {
    const onChange = () => setRoute(parseHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function href(path, query) {
  const q = query ? new URLSearchParams(Object.entries(query).filter(([, v]) => v !== "" && v != null && v !== false)).toString() : "";
  return `#${path}${q ? `?${q}` : ""}`;
}

export function navigate(path, query) {
  window.location.hash = href(path, query).slice(1);
}

/* ---------- data loading ---------- */
export function useData(loader, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const seq = useRef(0);
  const reload = useCallback(() => {
    const id = ++seq.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    loader()
      .then((data) => id === seq.current && setState({ data, error: null, loading: false }))
      .catch((error) => id === seq.current && setState((s) => ({ ...s, error, loading: false })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(reload, [reload]);
  return { ...state, reload };
}

/* ---------- statuses ---------- */
export const BUCKETS = [
  { key: "done", label: "Terminé" },
  { key: "review", label: "En review" },
  { key: "in_progress", label: "En cours" },
  { key: "waiting", label: "En attente" },
  { key: "other", label: "Autre" },
];

const DONE = new Set(["fin", "apr", "cmpt", "clsd", "na", "omt", "cbb", "dlvr", "vwd", "res", "cfrm", "recd", "valide", "cliapp", "intapp"]);
const REVIEW = new Set(["rev", "av", "rsb", "pub"]);
const PROGRESS = new Set(["ip", "act", "wip", "ren", "rtk", "tr"]);
const WAITING = new Set(["wtg", "rdy", "rdysta", "hld", "opn", "pndng"]);

export function bucketOf(status) {
  const s = (status || "").toLowerCase();
  if (DONE.has(s)) return "done";
  if (REVIEW.has(s)) return "review";
  if (PROGRESS.has(s)) return "in_progress";
  if (WAITING.has(s) || !s) return "waiting";
  return "other";
}

/* ---------- formatting ---------- */
const nf = new Intl.NumberFormat("fr-FR");
export const num = (n) => nf.format(n ?? 0);

export function plural(n, one, many) {
  return `${num(n)} ${n === 1 ? one : many}`;
}

const df = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", year: "numeric" });
const dfShort = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });

export function fmtDate(value, short = false) {
  if (!value) return "";
  const d = new Date(String(value).length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(d.getTime())) return String(value);
  return (short && d.getFullYear() === new Date().getFullYear() ? dfShort : df).format(d);
}

export function relTime(value) {
  if (!value) return "";
  const d = new Date(value);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (Number.isNaN(diff)) return "";
  if (diff < 60) return "à l'instant";
  if (diff < 3600) return `il y a ${Math.round(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.round(diff / 3600)} h`;
  if (diff < 86400 * 30) return `il y a ${Math.round(diff / 86400)} j`;
  return fmtDate(value);
}

export function daysLate(due) {
  if (!due) return 0;
  const d = new Date(`${String(due).slice(0, 10)}T00:00:00`);
  return Math.max(0, Math.floor((Date.now() - d.getTime()) / 86400000));
}

export const linkName = (v) => (v && typeof v === "object" ? v.name || v.code : v) || "";
export const linkNames = (v) => (Array.isArray(v) ? v.map(linkName).filter(Boolean) : v ? [linkName(v)] : []);

export function taskName(t) {
  return t.content || t.name || t.cached_display_name || `Tâche ${t.id}`;
}

export function recordName(r) {
  return r.name || r.code || r.content || r.subject || r.cached_display_name || `#${r.id}`;
}
