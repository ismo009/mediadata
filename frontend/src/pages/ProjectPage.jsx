import React, { useState } from "react";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { api } from "../api";
import { useApp } from "../App";
import { daysLate, fmtDate, href, linkName, linkNames, navigate, num, plural, recordName, relTime, taskName, useData } from "../lib";
import TaskTable from "../components/TaskTable";
import { Empty, ErrorBox, LateChip, Legend, LoadingRows, SgLink, Status, StatusBar, Thumb } from "../components/ui";

const TABS = [
  { key: "summary", label: "Vue d'ensemble" },
  { key: "tasks", label: "Tâches", count: "Task" },
  { key: "shots", label: "Plans", count: "Shot" },
  { key: "team", label: "Équipe" },
  { key: "notes", label: "Notes", count: "Note" },
  { key: "versions", label: "Versions", count: "Version" },
  { key: "assets", label: "Assets", count: "Asset" },
];

export default function ProjectPage({ id, tab, query }) {
  const details = useData(() => api.project(id), [id]);
  const setQuery = (q) => navigate(`/projects/${id}/${tab}`, q);

  if (details.error) return <div className="page"><ErrorBox error={details.error} onRetry={details.reload} /></div>;
  if (!details.data) return <div className="page"><LoadingRows rows={10} /></div>;
  const d = details.data;
  const p = d.project;
  const total = d.counts.Task || 0;
  const pct = total ? Math.round((d.tasks.done / total) * 100) : null;
  const tabs = TABS.filter((t) => !t.count || d.counts[t.count] || t.key === "tasks");

  return (
    <div className="page">
      <a className="back" href="#/"><ArrowLeft size={15} /> Productions</a>

      <div className="project-head">
        <div>
          <h1 className="display h1">{p.name}</h1>
          <div className="facts">
            <span className={`pill ${p.is_active ? "on" : ""}`}>{p.status_label}</span>
            {p.end_date && <span>Fin prévue le {fmtDate(p.end_date)}</span>}
          </div>
        </div>
        {p.source_url && (
          <a className="btn" href={p.source_url} target="_blank" rel="noreferrer">
            <ExternalLink size={14} /> ShotGrid
          </a>
        )}
      </div>

      <div className="figures-row">
        <Figure value={pct === null ? "—" : `${pct} %`} label="des tâches terminées" />
        <Figure value={num(total)} label="tâches" />
        <Figure value={d.late_tasks.length >= 50 ? "50+" : num(d.late_tasks.length)} label="en retard" alert={d.late_tasks.length > 0} />
        <Figure value={num(d.counts.Shot || 0)} label="plans" />
      </div>

      <nav className="tabs" aria-label="Sections de la production">
        {tabs.map((t) => (
          <a key={t.key} className="tab" href={href(`/projects/${id}/${t.key === "summary" ? "" : t.key}`)} aria-current={tab === t.key ? "page" : undefined}>
            {t.label}
            {t.count && <span className="count">{num(d.counts[t.count] || 0)}</span>}
          </a>
        ))}
      </nav>

      {tab === "summary" && <Summary d={d} id={id} />}
      {tab === "tasks" && <TaskTable base={{ project_id: id }} query={query} setQuery={setQuery} steps={d.steps} people={d.people} />}
      {tab === "shots" && <Shots d={d} id={id} query={query} setQuery={setQuery} />}
      {tab === "team" && <Team d={d} id={id} />}
      {tab === "notes" && <Notes id={id} />}
      {tab === "versions" && <Gallery entityType="Version" id={id} sort="recent" />}
      {tab === "assets" && <Gallery entityType="Asset" id={id} />}
    </div>
  );
}

function Figure({ value, label, alert = false }) {
  return (
    <div className={`figure ${alert ? "alert" : ""}`}>
      <span className="value">{value}</span>
      <span className="label">{label}</span>
    </div>
  );
}

function Summary({ d, id }) {
  const { labels } = useApp();
  const [showAllSteps, setShowAllSteps] = useState(false);
  const watch = [
    ...d.late_tasks.map((t) => ({ t, why: <LateChip days={daysLate(t.due_date)} /> })),
    ...d.blocked_tasks
      .filter((t) => !t.late)
      .map((t) => ({ t, why: <span className="muted small">attend {linkNames(t.upstream_tasks).join(", ")}</span> })),
  ];
  const steps = showAllSteps ? d.steps : d.steps.slice(0, 6);

  return (
    <div className="stack">
      <section>
        <div className="section-head">
          <h2 className="h3">À surveiller</h2>
          {d.late_tasks.length > 0 && (
            <a className="small" href={href(`/projects/${id}/tasks`, { late: "1" })}>
              Voir {d.late_tasks.length >= 50 ? "toutes les" : `les ${d.late_tasks.length}`} tâches en retard
            </a>
          )}
        </div>
        {watch.length ? (
          <div className="list">
            {watch.slice(0, 5).map(({ t, why }) => (
              <div key={t.id} className="row">
                <span className="primary">{taskName(t)} <span className="faint">· {linkName(t.entity)}</span></span>
                <span className="secondary">
                  {[linkName(t.step), linkNames(t.task_assignees).join(", ") || "non assignée"].filter(Boolean).join(" · ")}
                  {" · "}
                  <Status code={t.sg_status_list} labels={labels} />
                </span>
                <span className="aside">{why}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">Rien à signaler : aucune tâche en retard ni bloquée.</p>
        )}
      </section>

      <section>
        <div className="section-head">
          <h2 className="h3">Avancement par étape</h2>
          <Legend keys={["done", "review", "in_progress", "waiting"]} />
        </div>
        {d.steps.length ? (
          <>
            {steps.map((s) => {
              const total = s.done + s.review + s.in_progress + s.waiting + s.other;
              return (
                <a key={s.step} className="matrix-row" href={s.step_id ? href(`/projects/${id}/tasks`, { step: s.step_id }) : href(`/projects/${id}/tasks`)}>
                  <span className="label">{s.step}</span>
                  <StatusBar counts={s} />
                  <span className="n">{Math.round((s.done / total) * 100)} %</span>
                </a>
              );
            })}
            {d.steps.length > 6 && (
              <button className="btn ghost" style={{ marginTop: 8 }} onClick={() => setShowAllSteps((v) => !v)}>
                {showAllSteps ? "Afficher moins" : `Afficher les ${d.steps.length} étapes`}
              </button>
            )}
          </>
        ) : (
          <Empty>Aucune tâche dans cette production.</Empty>
        )}
      </section>
    </div>
  );
}

function Team({ d, id }) {
  if (!d.people.length) return <Empty>Aucune tâche n'est assignée dans cette production.</Empty>;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr><th>Personne</th><th className="num">Tâches ouvertes</th><th className="num">Total</th><th aria-label="Voir les tâches" /></tr>
        </thead>
        <tbody>
          {d.people.map((u) => (
            <tr key={u.id}>
              <td><a href={href(`/people/${u.id}`)}>{u.name}</a></td>
              <td className="num">{num(u.open)}</td>
              <td className="num muted">{num(u.tasks)}</td>
              <td className="num"><a className="small" href={href(`/projects/${id}/tasks`, { person: u.id })}>Ses tâches</a></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Shots({ d, id, query, setQuery }) {
  const { labels } = useApp();
  const seq = query.seq ? Number(query.seq) : null;
  const page = Number(query.page || 1);
  const shots = useData(
    () => api.records("Shot", { project_id: id, sequence_id: seq, sort: "name", page, limit: 60 }),
    [id, seq, page]
  );
  return (
    <div>
      {d.sequences.length > 1 && (
        <div className="toolbar">
          <select className="select" value={seq || ""} onChange={(e) => setQuery({ seq: e.target.value })} aria-label="Séquence">
            <option value="">Toutes les séquences</option>
            {d.sequences.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
      )}
      {shots.error ? (
        <ErrorBox error={shots.error} onRetry={shots.reload} />
      ) : !shots.data ? (
        <LoadingRows />
      ) : !shots.data.records.length ? (
        <Empty>Aucun plan.</Empty>
      ) : (
        <>
          <div className="shot-grid">
            {shots.data.records.map((s) => (
              <a key={s.id} className="shot-card" href={href(`/projects/${id}/tasks`, { q: recordName(s) })}>
                <Thumb entityType="Shot" id={s.id} alt={recordName(s)} />
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span className="name">{recordName(s)}</span>
                  <Status code={s.sg_status_list} labels={labels} />
                </div>
              </a>
            ))}
          </div>
          <Pager data={shots.data} page={page} onPage={(n) => setQuery({ ...query, page: String(n) })} unit="plans" />
        </>
      )}
    </div>
  );
}

function Gallery({ entityType, id, sort = "name" }) {
  const { labels } = useApp();
  const [page, setPage] = useState(1);
  const data = useData(() => api.records(entityType, { project_id: id, sort, page, limit: 48 }), [entityType, id, page]);
  if (data.error) return <ErrorBox error={data.error} onRetry={data.reload} />;
  if (!data.data) return <LoadingRows />;
  if (!data.data.records.length) return <Empty>Aucun élément.</Empty>;
  return (
    <>
      <div className="shot-grid">
        {data.data.records.map((r) => (
          <a key={r.id} className="shot-card" href={r.source_url} target="_blank" rel="noreferrer">
            <Thumb entityType={entityType} id={r.id} alt={recordName(r)} />
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span className="name">{recordName(r)}</span>
              <Status code={r.sg_status_list} labels={labels} />
            </div>
            <span className="faint small">
              {[linkName(r.entity), linkName(r.user)].filter(Boolean).join(", ")}
              {entityType === "Version" && r.created_at ? `, ${relTime(r.created_at)}` : ""}
            </span>
          </a>
        ))}
      </div>
      <Pager data={data.data} page={page} onPage={setPage} unit={entityType === "Version" ? "versions" : "assets"} />
    </>
  );
}

function Notes({ id }) {
  const [page, setPage] = useState(1);
  const notes = useData(() => api.records("Note", { project_id: id, sort: "recent", page, limit: 30 }), [id, page]);
  if (notes.error) return <ErrorBox error={notes.error} onRetry={notes.reload} />;
  if (!notes.data) return <LoadingRows />;
  if (!notes.data.records.length) return <Empty>Aucune note sur cette production.</Empty>;
  return (
    <>
      {notes.data.records.map((n) => (
        <article key={n.id} className="note">
          <div className="note-head">
            <strong>{n.subject || "Note"}</strong>
            <span className="faint small">
              {linkName(n.user)}, {fmtDate(n.created_at)} <SgLink url={n.source_url} />
            </span>
          </div>
          {n.content && <p className="note-body">{n.content}</p>}
          {n.note_links?.length > 0 && (
            <div className="note-links">
              {linkNames(n.note_links).map((l) => <span key={l} className="pill">{l}</span>)}
            </div>
          )}
        </article>
      ))}
      <Pager data={notes.data} page={page} onPage={setPage} unit="notes" />
    </>
  );
}

function Pager({ data, page, onPage, unit }) {
  if (data.pages <= 1) return <p className="faint small" style={{ marginTop: 14 }}>{plural(data.total, unit.replace(/s$/, ""), unit)}</p>;
  return (
    <div className="pager">
      <span>{num(data.total)} {unit}</span>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <button className="btn" disabled={page <= 1} onClick={() => onPage(page - 1)}>Précédent</button>
        <span>Page {page} sur {data.pages}</span>
        <button className="btn" disabled={page >= data.pages} onClick={() => onPage(page + 1)}>Suivant</button>
      </div>
    </div>
  );
}
