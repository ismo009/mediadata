import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { LayoutList, Menu, Moon, RefreshCw, Search, Sparkles, Sun, Users, X, DatabaseZap } from "lucide-react";
import { api } from "./api";
import { href, relTime, useData, useRoute } from "./lib";
import { StatusBar } from "./components/ui";
import SearchPalette from "./components/SearchPalette";
import Assistant from "./components/Assistant";
import Overview from "./pages/Overview";
import ProjectPage from "./pages/ProjectPage";
import PeoplePage from "./pages/PeoplePage";
import PersonPage from "./pages/PersonPage";
import SyncPage from "./pages/SyncPage";

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

function readTheme() {
  try {
    return localStorage.getItem("theme") || "";
  } catch {
    return "";
  }
}

export default function App() {
  const route = useRoute();
  const dashboard = useData(() => api.dashboard(), []);
  const statuses = useData(() => api.statuses(), []);
  const [assistantOpen, setAssistantOpen] = useState(() => window.innerWidth > 1280);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [theme, setTheme] = useState(readTheme);
  const [sync, setSync] = useState(null);

  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* private mode */
    }
  }, [theme]);

  useEffect(() => setRailOpen(false), [route.path]);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Sync status: poll fast while a sync runs, slowly otherwise; refresh data when it ends.
  useEffect(() => {
    let timer;
    let wasRunning = false;
    const tick = async () => {
      try {
        const { last_sync } = await api.syncStatus();
        setSync(last_sync);
        const running = last_sync?.status === "running";
        if (wasRunning && !running) {
          dashboard.reload();
          statuses.reload();
        }
        wasRunning = running;
        timer = setTimeout(tick, running ? 2500 : 30000);
      } catch {
        timer = setTimeout(tick, 30000);
      }
    };
    tick();
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startSync = async (mode = "auto") => {
    try {
      await api.startSync(mode);
      setSync((s) => ({ ...(s || {}), status: "running", records_count: 0 }));
      setTimeout(async () => setSync((await api.syncStatus()).last_sync), 800);
    } catch (e) {
      alert(e.message);
    }
  };

  const projectId = route.parts[0] === "projects" ? Number(route.parts[1]) : null;
  const ctx = useMemo(
    () => ({
      dashboard,
      labels: statuses.data?.statuses || {},
      sync,
      startSync,
      projectName: (id) => dashboard.data?.projects.find((p) => p.id === id)?.name,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [dashboard, statuses.data, sync]
  );

  let page;
  if (route.parts[0] === "projects" && projectId) page = <ProjectPage key={projectId} id={projectId} tab={route.parts[2] || "summary"} query={route.query} />;
  else if (route.parts[0] === "people" && route.parts[1]) page = <PersonPage key={route.parts[1]} id={Number(route.parts[1])} />;
  else if (route.parts[0] === "people") page = <PeoplePage />;
  else if (route.parts[0] === "sync") page = <SyncPage />;
  else page = <Overview />;

  return (
    <AppContext.Provider value={ctx}>
      <div className={`shell ${assistantOpen ? "with-assistant" : ""}`}>
        <Rail route={route} projectId={projectId} open={railOpen} onClose={() => setRailOpen(false)} />
        <div className="main">
          <header className="topbar">
            <button className="btn icon ghost only-mobile" onClick={() => setRailOpen(true)} aria-label="Ouvrir le menu">
              <Menu size={18} />
            </button>
            <button className="btn ghost" onClick={() => setPaletteOpen(true)} style={{ color: "var(--ink-2)" }}>
              <Search size={15} />
              <span className="hide-mobile">Rechercher</span>
              <kbd className="hide-mobile">Ctrl K</kbd>
            </button>
            <div className="grow" />
            <SyncIndicator sync={sync} onSync={() => startSync("auto")} />
            <button
              className="btn icon ghost"
              onClick={() => setTheme(theme === "dark" ? "light" : theme === "light" ? "" : "dark")}
              aria-label="Changer de thème"
              title={theme === "dark" ? "Thème sombre" : theme === "light" ? "Thème clair" : "Thème du système"}
            >
              {theme === "dark" ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            <button className="btn" aria-pressed={assistantOpen} onClick={() => setAssistantOpen((o) => !o)}>
              <Sparkles size={15} />
              Lia
            </button>
          </header>
          <main className="content">{page}</main>
        </div>
        {assistantOpen && <Assistant projectId={projectId} onClose={() => setAssistantOpen(false)} />}
      </div>
      {paletteOpen && <SearchPalette onClose={() => setPaletteOpen(false)} />}
    </AppContext.Provider>
  );
}

function SyncIndicator({ sync, onSync }) {
  const running = sync?.status === "running";
  const failed = sync?.status === "failed";
  const label = running
    ? `Synchronisation… ${sync.records_count ? `${sync.records_count} enregistrements` : ""}`
    : failed
    ? "Dernière synchro échouée"
    : sync?.finished_at
    ? `Synchronisé ${relTime(sync.finished_at)}`
    : "Jamais synchronisé";
  return (
    <button className="btn ghost" onClick={onSync} disabled={running} title={failed ? sync.error : "Synchroniser avec ShotGrid"}>
      <RefreshCw size={15} className={running ? "spin" : ""} style={running ? { animation: "spin 1s linear infinite" } : undefined} />
      <span className={`hide-mobile ${failed ? "late-text" : "muted"}`}>{label}</span>
      <style>{"@keyframes spin{to{transform:rotate(360deg)}}"}</style>
    </button>
  );
}

function Rail({ route, projectId, open, onClose }) {
  const { dashboard } = useApp();
  const [filter, setFilter] = useState("");
  const [showAll, setShowAll] = useState(false);
  const projects = dashboard.data?.projects || [];
  const visible = projects
    .filter((p) => (showAll ? true : p.is_active))
    .filter((p) => !filter || p.name.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => (b.tasks_late || 0) - (a.tasks_late || 0) || a.name.localeCompare(b.name, "fr"));

  const nav = [
    { to: "/", label: "Vue d'ensemble", icon: LayoutList, current: route.parts.length === 0 },
    { to: "/people", label: "Équipe", icon: Users, current: route.parts[0] === "people" },
    { to: "/sync", label: "Synchronisation", icon: DatabaseZap, current: route.parts[0] === "sync" },
  ];
  return (
    <>
      {open && <div className="palette-backdrop" style={{ zIndex: 34, background: "rgba(0,0,0,.25)" }} onClick={onClose} />}
      <aside className={`rail ${open ? "open" : ""}`}>
        <div className="rail-head">
          <a className="brand" href="#/">MedIAData</a>
          <div style={{ flex: 1 }} />
          <button className="btn icon ghost only-mobile" onClick={onClose} aria-label="Fermer le menu">
            <X size={16} />
          </button>
        </div>
        <nav className="rail-nav">
          {nav.map(({ to, label, icon: Icon, current }) => (
            <a key={to} className="rail-link" href={href(to)} aria-current={current ? "page" : undefined}>
              <Icon size={16} />
              {label}
            </a>
          ))}
        </nav>
        <div className="rail-section">
          <span className="h3">Productions</span>
          <div className="segmented" role="group" aria-label="Filtrer les productions">
            <button aria-pressed={!showAll} onClick={() => setShowAll(false)}>Actives</button>
            <button aria-pressed={showAll} onClick={() => setShowAll(true)}>Toutes</button>
          </div>
        </div>
        <div className="rail-filter">
          <div className="search-field">
            <Search size={14} />
            <input className="input" placeholder="Filtrer…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filtrer les productions" />
          </div>
        </div>
        <div className="bin">
          {dashboard.loading && !dashboard.data
            ? Array.from({ length: 8 }, (_, i) => <div key={i} className="skeleton" style={{ height: 36, margin: "6px 10px" }} />)
            : visible.map((p) => (
                <a
                  key={p.id}
                  href={href(`/projects/${p.id}`)}
                  className={`bin-item ${p.is_active ? "" : "inactive"}`}
                  aria-current={p.id === projectId ? "page" : undefined}
                >
                  <span className="name">{p.name}</span>
                  <span className="meta">
                    {p.tasks_late ? <span className="late-text">{p.tasks_late}</span> : p.tasks_total || ""}
                  </span>
                  <div className="bar">
                    <StatusBar counts={p.tasks} size="thin" />
                  </div>
                </a>
              ))}
          {dashboard.data && !visible.length && <p className="muted small" style={{ padding: "8px 10px" }}>Aucune production ne correspond.</p>}
        </div>
      </aside>
    </>
  );
}
