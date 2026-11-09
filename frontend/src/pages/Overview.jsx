import React, { useState } from "react";
import { useApp } from "../App";
import { href, linkName, num, plural, relTime } from "../lib";
import { ErrorBox, LateChip, Legend, LoadingRows, StatusBar } from "../components/ui";

const SORTS = [
  { key: "late", label: "Retard" },
  { key: "activity", label: "Activité" },
  { key: "name", label: "Nom" },
];

export default function Overview() {
  const { dashboard } = useApp();
  const [sort, setSort] = useState("late");
  const [scope, setScope] = useState("active");

  if (dashboard.error && !dashboard.data) return <div className="page"><ErrorBox error={dashboard.error} onRetry={dashboard.reload} /></div>;
  const d = dashboard.data;

  const projects = (d?.projects || [])
    .filter((p) => (scope === "active" ? p.is_active : true))
    .filter((p) => scope !== "active" || p.tasks_total > 0 || p.shots_total > 0)
    .sort((a, b) => {
      if (sort === "late") return b.tasks_late - a.tasks_late || (b.last_activity || "").localeCompare(a.last_activity || "");
      if (sort === "activity") return (b.last_activity || "").localeCompare(a.last_activity || "");
      return a.name.localeCompare(b.name, "fr");
    });
  const slipping = (d?.projects || []).filter((p) => p.is_active && p.tasks_late > 0);

  return (
    <div className="page">
      {!d ? (
        <LoadingRows rows={10} />
      ) : (
        <>
          <h1 className="display h1 headline">
            {d.tasks_late
              ? `${plural(d.tasks_late, "tâche en retard", "tâches en retard")} sur ${plural(slipping.length, "production", "productions")}`
              : "Aucune tâche en retard"}
          </h1>
          <p className="headline-sub">
            {plural(d.projects_active, "production active", "productions actives")}, {num(d.tasks_review)} tâches attendent une validation et{" "}
            {num(d.shots_total)} plans sont suivis dans ShotGrid.
          </p>

          <div className="overview">
            <section aria-labelledby="strips-title">
              <div className="strips-head">
                <h2 id="strips-title" className="h3">Avancement des tâches par production</h2>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <div className="segmented" role="group" aria-label="Productions affichées">
                    <button aria-pressed={scope === "active"} onClick={() => setScope("active")}>Actives</button>
                    <button aria-pressed={scope === "all"} onClick={() => setScope("all")}>Toutes</button>
                  </div>
                  <div className="segmented" role="group" aria-label="Trier par">
                    {SORTS.map((s) => (
                      <button key={s.key} aria-pressed={sort === s.key} onClick={() => setSort(s.key)}>{s.label}</button>
                    ))}
                  </div>
                </div>
              </div>
              <div style={{ padding: "10px 0 4px" }}><Legend /></div>
              {projects.map((p) => (
                <a key={p.id} className="strip" href={href(`/projects/${p.id}`)}>
                  <div style={{ minWidth: 0 }}>
                    <div className="title">{p.name}</div>
                    <div className="sub">
                      {p.is_active ? "" : `${p.status_label} · `}
                      {p.last_activity ? `Activité ${relTime(p.last_activity)}` : "Aucune activité"}
                    </div>
                  </div>
                  <div className="sbar-cell"><StatusBar counts={p.tasks} /></div>
                  <div className="figures">
                    {p.tasks_late ? <LateChip count={p.tasks_late} compact /> : null}
                    <div>{plural(p.tasks_total, "tâche", "tâches")}</div>
                  </div>
                </a>
              ))}
              {!projects.length && <p className="muted" style={{ padding: "16px 0" }}>Aucune production avec des tâches.</p>}
            </section>

            <aside aria-labelledby="notes-title">
              <div className="strips-head">
                <h2 id="notes-title" className="h3">Dernières notes</h2>
              </div>
              <div className="feed">
                {d.recent_notes.map((n) => (
                  <article key={n.id} className="feed-item">
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                      <a href={href(`/projects/${n.project?.id}/notes`)} style={{ fontWeight: 550, textDecoration: "none" }}>
                        {n.subject || linkName(n.note_links?.[0]) || "Note"}
                      </a>
                      <span className="faint small">{relTime(n.created_at)}</span>
                    </div>
                    <div className="who">
                      {linkName(n.user)} · {linkName(n.project)}
                    </div>
                    {n.content && <p>{n.content}</p>}
                  </article>
                ))}
              </div>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
