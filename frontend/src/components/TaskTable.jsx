import React from "react";
import { Search } from "lucide-react";
import { api } from "../api";
import { useApp } from "../App";
import { daysLate, fmtDate, href, linkName, linkNames, num, taskName, useData } from "../lib";
import { Empty, ErrorBox, LateChip, LoadingRows, SgLink, Status } from "./ui";

const BUCKET_FILTERS = [
  { key: "", label: "Tous" },
  { key: "waiting", label: "En attente" },
  { key: "in_progress", label: "En cours" },
  { key: "review", label: "En review" },
  { key: "done", label: "Terminé" },
];

/* Filterable, paginated task table. Filters live in `query` (URL) and change via `setQuery`. */
export default function TaskTable({ base, query, setQuery, steps = [], people = [], showProject = false }) {
  const { labels } = useApp();
  const page = Number(query.page || 1);
  const params = {
    ...base,
    step_id: query.step,
    person_id: query.person,
    bucket: query.bucket,
    late: query.late === "1",
    blocked: query.blocked === "1",
    search: query.q,
    sort: query.sort || "due",
    page,
    limit: 50,
  };
  const { data, error, loading, reload } = useData(() => api.records("Task", params), [JSON.stringify(params)]);
  const set = (patch) => setQuery({ ...query, page: "", ...patch });

  return (
    <div>
      <div className="toolbar">
        <div className="search-field grow">
          <Search size={14} />
          <input
            className="input"
            placeholder="Rechercher une tâche…"
            defaultValue={query.q || ""}
            onKeyDown={(e) => e.key === "Enter" && set({ q: e.currentTarget.value })}
            onBlur={(e) => e.currentTarget.value !== (query.q || "") && set({ q: e.currentTarget.value })}
            aria-label="Rechercher une tâche"
          />
        </div>
        {steps.length > 0 && (
          <select className="select" value={query.step || ""} onChange={(e) => set({ step: e.target.value })} aria-label="Étape">
            <option value="">Toutes les étapes</option>
            {steps.filter((s) => s.step_id).map((s) => (
              <option key={s.step_id} value={s.step_id}>{s.step}</option>
            ))}
          </select>
        )}
        {people.length > 0 && (
          <select className="select" value={query.person || ""} onChange={(e) => set({ person: e.target.value })} aria-label="Personne">
            <option value="">Tout le monde</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        )}
        <select className="select" value={query.sort || "due"} onChange={(e) => set({ sort: e.target.value })} aria-label="Trier">
          <option value="due">Par échéance</option>
          <option value="updated">Dernières modifiées</option>
          <option value="name">Par nom</option>
        </select>
      </div>
      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Statut">
          {BUCKET_FILTERS.map((b) => (
            <button key={b.key} aria-pressed={(query.bucket || "") === b.key} onClick={() => set({ bucket: b.key })}>
              {b.key && <i className={`dot ${b.key}`} />}
              {b.label}
            </button>
          ))}
        </div>
        <button className="btn" aria-pressed={query.late === "1"} onClick={() => set({ late: query.late === "1" ? "" : "1" })}>
          En retard
        </button>
        <button className="btn" aria-pressed={query.blocked === "1"} onClick={() => set({ blocked: query.blocked === "1" ? "" : "1" })}>
          Bloquées
        </button>
      </div>

      {error ? (
        <ErrorBox error={error} onRetry={reload} />
      ) : !data ? (
        <LoadingRows />
      ) : !data.records.length ? (
        <Empty>Aucune tâche ne correspond à ces filtres.</Empty>
      ) : (
        <>
          <div className="table-wrap" style={{ opacity: loading ? 0.6 : 1 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Tâche</th>
                  {showProject && <th>Production</th>}
                  <th>Élément</th>
                  <th className="hide-mobile">Étape</th>
                  <th className="hide-mobile">Assignée à</th>
                  <th>Statut</th>
                  <th>Échéance</th>
                  <th aria-label="Lien ShotGrid" />
                </tr>
              </thead>
              <tbody>
                {data.records.map((t) => (
                  <tr key={t.id}>
                    <td>{taskName(t)}</td>
                    {showProject && (
                      <td>
                        <a href={href(`/projects/${t.project?.id}/tasks`)}>{linkName(t.project)}</a>
                      </td>
                    )}
                    <td className="muted">{linkName(t.entity)}</td>
                    <td className="muted hide-mobile">{linkName(t.step)}</td>
                    <td className="muted hide-mobile">
                      {linkNames(t.task_assignees).map((n, i) => {
                        const p = t.task_assignees[i];
                        return (
                          <span key={i}>
                            {i > 0 && ", "}
                            {p?.type === "HumanUser" ? <a href={href(`/people/${p.id}`)}>{n}</a> : n}
                          </span>
                        );
                      })}
                    </td>
                    <td><Status code={t.sg_status_list} labels={labels} /></td>
                    <td>
                      {t.late ? <LateChip days={daysLate(t.due_date)} /> : <span className="muted">{fmtDate(t.due_date, true)}</span>}
                    </td>
                    <td><SgLink url={t.source_url} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <span>{num(data.total)} tâches</span>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <button className="btn" disabled={page <= 1} onClick={() => setQuery({ ...query, page: String(page - 1) })}>Précédent</button>
              <span>Page {page} sur {data.pages}</span>
              <button className="btn" disabled={page >= data.pages} onClick={() => setQuery({ ...query, page: String(page + 1) })}>Suivant</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
