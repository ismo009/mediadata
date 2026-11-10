import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { LogOut, Moon, RefreshCw, Search, Sparkles, Sun } from "lucide-react";
import { api } from "./api";
import { href, relTime, useData, useRoute } from "./lib";
import SearchPalette from "./components/SearchPalette";
import Assistant from "./components/Assistant";
import LoginPage from "./pages/LoginPage";
import MyTasksPage from "./pages/MyTasksPage";
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

/* Sign-in gate: the dashboard only exists for a signed-in ShotGrid user. */
export default function App() {
  const [theme, setTheme] = useState(readTheme);
  const [me, setMe] = useState(null);

  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* private mode */
    }
  }, [theme]);

  const loadMe = useCallback(() => {
    api.me().then(setMe).catch(() => setMe({ authenticated: false }));
  }, []);

  useEffect(() => {
    loadMe();
    window.addEventListener("auth-required", loadMe);
    return () => window.removeEventListener("auth-required", loadMe);
  }, [loadMe]);

  if (!me) return null;
  if (!me.authenticated) return <LoginPage info={me} />;

  const signOut = async () => {
    await api.logout();
    try {
      sessionStorage.clear();
    } catch {
      /* storage unavailable */
    }
    window.location.hash = "#/";
    loadMe();
  };
  return <Workspace key={me.id} me={me} theme={theme} setTheme={setTheme} onSignOut={signOut} />;
}

function Workspace({ me, theme, setTheme, onSignOut }) {
  const route = useRoute();
  const dashboard = useData(() => api.dashboard(), []);
  const statuses = useData(() => api.statuses(), []);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [sync, setSync] = useState(null);

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

  useEffect(() => {
    document.querySelector(".content")?.scrollTo(0, 0);
  }, [route.path]);

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
      me,
      dashboard,
      labels: statuses.data?.statuses || {},
      sync,
      startSync,
      projectName: (id) => dashboard.data?.projects.find((p) => p.id === id)?.name,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [me, dashboard, statuses.data, sync]
  );

  const section = route.parts[0] || "projects";
  let page;
  if (section === "projects" && projectId) page = <ProjectPage key={projectId} id={projectId} tab={route.parts[2] || "summary"} query={route.query} />;
  else if (section === "me") page = <MyTasksPage query={route.query} />;
  else if (section === "people" && route.parts[1]) page = <PersonPage key={route.parts[1]} id={Number(route.parts[1])} />;
  else if (section === "people") page = <PeoplePage />;
  else if (section === "sync" && me.is_admin) page = <SyncPage />;
  else page = <Overview />;

  const nav = [
    { key: "projects", to: "/", label: "Productions" },
    { key: "me", to: "/me", label: "Mes tâches" },
    { key: "people", to: "/people", label: "Équipe" },
    ...(me.is_admin ? [{ key: "sync", to: "/sync", label: "Synchronisation" }] : []),
  ];
  const current = ["me", "people", "sync"].includes(section) ? section : "projects";

  return (
    <AppContext.Provider value={ctx}>
      <div className={`shell ${assistantOpen ? "with-assistant" : ""}`}>
        <div className="main">
          <header className="topbar">
            <a className="brand" href="#/">MedIAData</a>
            <nav className="topnav" aria-label="Navigation principale">
              {nav.map((n) => (
                <a key={n.key} href={href(n.to)} aria-current={current === n.key ? "page" : undefined}>
                  {n.label}
                </a>
              ))}
            </nav>
            <div className="grow" />
            <button className="btn icon ghost" onClick={() => setPaletteOpen(true)} aria-label="Rechercher (Ctrl K)" title="Rechercher (Ctrl K)">
              <Search size={17} />
            </button>
            <SyncIndicator sync={sync} canSync={me.is_admin} onSync={() => startSync("auto")} />
            <button
              className="btn icon ghost"
              onClick={() => setTheme(theme === "dark" ? "light" : theme === "light" ? "" : "dark")}
              aria-label="Changer de thème"
              title={theme === "dark" ? "Thème sombre" : theme === "light" ? "Thème clair" : "Thème du système"}
            >
              {theme === "dark" ? <Moon size={17} /> : <Sun size={17} />}
            </button>
            <button className="btn" aria-pressed={assistantOpen} onClick={() => setAssistantOpen((o) => !o)}>
              <Sparkles size={15} />
              <span className="hide-mobile">Demander à Lia</span>
              <span className="only-mobile">Lia</span>
            </button>
            <UserMenu me={me} onSignOut={onSignOut} />
          </header>
          <main className="content">{page}</main>
        </div>
        {assistantOpen && <Assistant projectId={projectId} onClose={() => setAssistantOpen(false)} />}
      </div>
      {paletteOpen && <SearchPalette onClose={() => setPaletteOpen(false)} />}
    </AppContext.Provider>
  );
}

function SyncIndicator({ sync, canSync, onSync }) {
  const running = sync?.status === "running";
  const failed = sync?.status === "failed";
  const state = running
    ? "Synchronisation en cours…"
    : failed
    ? `Dernière synchronisation échouée : ${sync.error || ""}`
    : sync?.finished_at
    ? `Données synchronisées ${relTime(sync.finished_at)}.`
    : "Données jamais synchronisées.";
  const label = canSync && !running ? `${state} Cliquer pour synchroniser maintenant.` : state;
  return (
    <button
      className={`btn icon ghost ${failed && canSync ? "late-text" : ""}`}
      onClick={canSync ? onSync : undefined}
      disabled={running}
      aria-disabled={!canSync}
      style={canSync ? undefined : { cursor: "default" }}
      title={label}
      aria-label={label}
    >
      <RefreshCw size={17} style={running ? { animation: "spin 1s linear infinite" } : undefined} />
    </button>
  );
}

function initials(name) {
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

function UserMenu({ me, onSignOut }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => !ref.current?.contains(e.target) && setOpen(false);
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div className="user-menu" ref={ref}>
      <button className="avatar" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={`Compte : ${me.name}`} title={me.name}>
        {initials(me.name)}
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">
            <strong>{me.name}</strong>
            <span className="faint small">{me.email}</span>
            <span className="small muted">
              {me.role || "Sans rôle"} · {me.sees_all ? "voit toutes les productions" : `voit ${me.projects.length} production${me.projects.length > 1 ? "s" : ""}`}
            </span>
          </div>
          <button role="menuitem" className="menu-item" onClick={onSignOut}>
            <LogOut size={15} /> Se déconnecter
          </button>
        </div>
      )}
    </div>
  );
}
