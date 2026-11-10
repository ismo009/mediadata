import React, { useState } from "react";
import { Search } from "lucide-react";
import { useApp } from "../App";
import { href, num, plural, relTime } from "../lib";
import { ErrorBox, LateChip } from "../components/ui";

const SORTS = {
  activity: { label: "Activité récente", fn: (a, b) => (b.last_activity || "").localeCompare(a.last_activity || "") },
  late: { label: "Les plus en retard", fn: (a, b) => b.tasks_late - a.tasks_late || a.name.localeCompare(b.name, "fr") },
  name: { label: "Nom", fn: (a, b) => a.name.localeCompare(b.name, "fr") },
};

function progress(p) {
  return p.tasks_total ? Math.round((p.tasks.done / p.tasks_total) * 100) : null;
}

export default function Overview() {
  const { dashboard, me } = useApp();
  const mine = new Set(me.projects);
  const [filter, setFilter] = useState("");
  const [scope, setScope] = useState(mine.size ? "mine" : "active");
  const [sort, setSort] = useState("activity");

  if (dashboard.error && !dashboard.data) {
    return <div className="page"><ErrorBox error={dashboard.error} onRetry={dashboard.reload} /></div>;
  }
  const d = dashboard.data;
  const projects = (d?.projects || [])
    .filter((p) => (scope === "mine" ? mine.has(p.id) : scope === "active" ? p.is_active && p.tasks_total > 0 : true))
    .filter((p) => !filter || p.name.toLowerCase().includes(filter.toLowerCase()))
    .sort(SORTS[sort].fn);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="display h1">Productions</h1>
          {d && (
            <p className="muted" style={{ margin: "6px 0 0" }}>
              {scope === "mine"
                ? plural(projects.length, "production dont vous êtes membre", "productions dont vous êtes membre")
                : scope === "active"
                ? plural(projects.length, "production en cours", "productions en cours")
                : plural(d.projects_total, "production visible", "productions visibles")}
            </p>
          )}
        </div>
      </div>

      <div className="toolbar">
        <div className="search-field grow">
          <Search size={14} />
          <input className="input" placeholder="Rechercher une production…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Rechercher une production" />
        </div>
        <select className="select" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Trier">
          {Object.entries(SORTS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
        </select>
        <div className="segmented" role="group" aria-label="Productions affichées">
          {mine.size > 0 && <button aria-pressed={scope === "mine"} onClick={() => setScope("mine")}>Mes productions</button>}
          <button aria-pressed={scope === "active"} onClick={() => setScope("active")}>En cours</button>
          <button aria-pressed={scope === "all"} onClick={() => setScope("all")}>Toutes</button>
        </div>
      </div>

      {!d ? (
        <div className="card-grid" aria-busy="true">
          {Array.from({ length: 9 }, (_, i) => <div key={i} className="skeleton" style={{ height: 118, borderRadius: 10 }} />)}
        </div>
      ) : !projects.length ? (
        <p className="muted">
          {filter ? `Aucune production ne correspond à « ${filter} ».` : "Aucune production à afficher ici."}
        </p>
      ) : (
        <div className="card-grid">
          {projects.map((p) => {
            const pct = progress(p);
            return (
              <a key={p.id} className="project-card" href={href(`/projects/${p.id}`)}>
                <span className="title">{p.name}</span>
                <span className="faint small">
                  {!p.is_active ? `${p.status_label}, ` : ""}
                  {p.last_activity ? `activité ${relTime(p.last_activity)}` : "aucune activité"}
                </span>
                {pct === null ? (
                  <span className="faint small card-foot">Aucune tâche</span>
                ) : (
                  <>
                    <div className="progress" role="img" aria-label={`${pct} % des tâches terminées`}>
                      <div style={{ width: `${pct}%` }} />
                    </div>
                    <span className="card-foot">
                      <span className="small">
                        <b>{pct} %</b> <span className="muted">de {num(p.tasks_total)} tâches</span>
                      </span>
                      {p.tasks_late > 0 && <LateChip count={p.tasks_late} />}
                    </span>
                  </>
                )}
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
