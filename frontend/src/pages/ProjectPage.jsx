import React from "react";
import { ExternalLink } from "lucide-react";
import { api } from "../api";
import { useApp } from "../App";
import { daysLate, fmtDate, href, linkName, linkNames, navigate, num, plural, recordName, relTime, taskName, useData } from "../lib";
import TaskTable from "../components/TaskTable";
import { Empty, ErrorBox, LateChip, Legend, LoadingRows, SgLink, Status, StatusBar, Thumb } from "../components/ui";

const TABS = [
  { key: "summary", label: "Synthèse" },
  { key: "tasks", label: "Tâches", count: "Task" },
  { key: "shots", label: "Plans", count: "Shot" },
  { key: "assets", label: "Assets", count: "Asset" },
  { key: "notes", label: "Notes", count: "Note" },
  { key: "versions", label: "Versions", count: "Version" },
];

export default function ProjectPage({ id, tab, query }) {
  const details = useData(() => api.project(id), [id]);
  const setQuery = (q) => navigate(`/projects/${id}/${tab}`, q);

  if (details.error) return <div className="page"><ErrorBox error={details.error} onRetry={details.reload} /></div>;
  if (!details.data) return <div className="page"><LoadingRows rows={12} /></div>;
  const d = details.data;
  const p = d.project;
  const late = d.late_tasks.length;

  return (
    <div className="page">
      <div className="crumbs">
        <a href="#/">Vue d'ensemble</a>
        <span aria-hidden="true">/</span>
        <span>Production</span>
      </div>
      <div className="project-head">
        <h1 className="display h1" style={{ maxWidth: "24ch" }}>{p.name}</h1>
        {p.source_url && (
          <a className="btn" href={p.source_url} target="_blank" rel="noreferrer">
            <ExternalLink size={14} /> Ouvrir dans ShotGrid
          </a>
        )}
      </div>
      <div className="facts">
        <span className={`pill ${p.is_active ? "on" : ""}`}>{p.status_label}</span>
        {(p.start_date || p.end_date) && (
          <span>
            {p.start_date ? fmtDate(p.start_date) : "?"} → <b>{p.end_date ? fmtDate(p.end_date) : "sans date de fin"}</b>
          </span>
        )}
        <span><b>{num(d.counts.Task || 0)}</b> tâches</span>
        <span><b>{num(d.counts.Shot || 0)}</b> plans</span>
        {d.hours_logged > 0 && <span><b>{num(d.hours_logged)} h</b> saisies</span>}
        {late > 0 && <LateChip count={late >= 50 ? "50+" : late} />}
      </div>
      <StatusBar counts={d.tasks} size="thick" />
      <div style={{ marginTop: 8 }}><Legend /></div>

      <nav className="tabs" aria-label="Sections de la production">
        {TABS.map((t) => (
          <a key={t.key} className="tab" href={href(`/projects/${id}/${t.key === "summary" ? "" : t.key}`)} aria-current={tab === t.key ? "page" : undefined}>
            {t.label}
            {t.count && <span className="count">{num(d.counts[t.count] || 0)}</span>}
          </a>
        ))}
      </nav>

      {tab === "summary" && <Summary d={d} id={id} />}
      {tab === "tasks" && <TaskTable base={{ project_id: id }} query={query} setQuery={setQuery} steps={d.steps} people={d.people} />}
      {tab === "shots" && <Shots d={d} id={id} query={query} setQuery={setQuery} />}
      {tab === "assets" && <Gallery entityType="Asset" id={id} />}
      {tab === "notes" && <Notes id={id} />}
      {tab === "versions" && <Gallery entityType="Version" id={id} sort="recent" />}
    </div>
  );
}

function Summary({ d, id }) {
  const { labels } = useApp();
  return (
    <div className="grid-2">
      <div>
        <section className="section">
          <div className="section-head">
            <h2 className="h3">Par étape</h2>
            <span className="faint small">Cliquez une étape pour voir ses tâches</span>
          </div>
          {d.steps.length ? (
            d.steps.map((s) => {
              const total = s.done + s.review + s.in_progress + s.waiting + s.other;
              return (
                <a key={s.step} className="matrix-row" href={s.step_id ? href(`/projects/${id}/tasks`, { step: s.step_id }) : href(`/projects/${id}/tasks`)}>
                  <span className="label">{s.step}</span>
                  <StatusBar counts={s} />
                  <span className="n">{Math.round((s.done / total) * 100)} % · {num(total)}</span>
                </a>
              );
            })
          ) : (
            <Empty>Aucune tâche dans cette production.</Empty>
          )}
        </section>

        <section className="section">
          <div className="section-head">
            <h2 className="h3">En retard</h2>
            {d.late_tasks.length > 0 && <a className="small" href={href(`/projects/${id}/tasks`, { late: "1" })}>Voir tout</a>}
          </div>
          {d.late_tasks.length ? (
            <div className="list">
              {d.late_tasks.slice(0, 10).map((t) => (
                <div key={t.id} className="row">
                  <span className="primary">{taskName(t)} <span className="faint">· {linkName(t.entity)}</span></span>
                  <span className="secondary">{linkName(t.step)} · {linkNames(t.task_assignees).join(", ") || "non assignée"} · <Status code={t.sg_status_list} labels={labels} /></span>
                  <span className="aside"><LateChip days={daysLate(t.due_date)} /></span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">Aucune tâche en retard.</p>
          )}
        </section>

        {d.blocked_tasks.length > 0 && (
          <section className="section">
            <div className="section-head">
              <h2 className="h3">Bloquées par une tâche amont</h2>
              <a className="small" href={href(`/projects/${id}/tasks`, { blocked: "1" })}>Voir tout</a>
            </div>
            <div className="list">
              {d.blocked_tasks.slice(0, 8).map((t) => (
                <div key={t.id} className="row">
                  <span className="primary">{taskName(t)}</span>
                  <span className="secondary">attend {linkNames(t.upstream_tasks).join(", ")}</span>
                  <span className="aside"><Status code={t.sg_status_list} labels={labels} /></span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      <div>
        {d.sequences.length > 0 && (
          <section className="section">
            <div className="section-head">
              <h2 className="h3">Séquences</h2>
              <span className="faint small">Avancement des plans</span>
            </div>
            {d.sequences.map((s) => (
              <a key={s.id} className="matrix-row" href={href(`/projects/${id}/shots`, { seq: s.id })}>
                <span className="label">{s.name}</span>
                <StatusBar counts={s.shots} unit="plan" units="plans" />
                <span className="n">{num(Object.values(s.shots).reduce((a, b) => a + b, 0))}</span>
              </a>
            ))}
          </section>
        )}

        <section className="section">
          <h2 className="h3" style={{ marginBottom: 10 }}>Équipe</h2>
          {d.people.length ? (
            <div className="list">
              {d.people.slice(0, 12).map((u) => (
                <div key={u.id} className="row">
                  <a className="primary" href={href(`/people/${u.id}`)}>{u.name}</a>
                  <span className="aside muted">{u.open} ouvertes / {u.tasks}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">Aucune tâche assignée.</p>
          )}
        </section>

        <section className="section">
          <div className="section-head">
            <h2 className="h3">Dernières notes</h2>
            <a className="small" href={href(`/projects/${id}/notes`)}>Toutes les notes</a>
          </div>
          {d.recent_notes.length ? (
            <div className="feed">
              {d.recent_notes.slice(0, 5).map((n) => (
                <article key={n.id} className="feed-item">
                  <div style={{ fontWeight: 550 }}>{n.subject || "Note"}</div>
                  <div className="who">{linkName(n.user)}, {relTime(n.created_at)}</div>
                  {n.content && <p>{n.content}</p>}
                </article>
              ))}
            </div>
          ) : (
            <p className="muted">Aucune note.</p>
          )}
        </section>
      </div>
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
      {d.sequences.length > 0 && (
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
                {s.description && <span className="faint small">{String(s.description).slice(0, 80)}</span>}
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
  const [page, setPage] = React.useState(1);
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
              {[linkName(r.entity), linkName(r.user), linkName(r.sg_asset_type)].filter(Boolean).join(", ")}
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
  const [page, setPage] = React.useState(1);
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
          {(n.note_links?.length > 0 || n.addressings_to?.length > 0) && (
            <div className="note-links">
              {linkNames(n.note_links).map((l) => <span key={l} className="pill">{l}</span>)}
              {linkNames(n.addressings_to).length > 0 && <span className="faint small">pour {linkNames(n.addressings_to).join(", ")}</span>}
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
