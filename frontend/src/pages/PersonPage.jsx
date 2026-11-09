import React, { useState } from "react";
import { api } from "../api";
import { useApp } from "../App";
import { bucketOf, daysLate, fmtDate, href, linkName, num, plural, taskName, useData } from "../lib";
import { Empty, ErrorBox, LateChip, Legend, LoadingRows, SgLink, Status, StatusBar } from "../components/ui";

export default function PersonPage({ id }) {
  const { labels } = useApp();
  const { data, error, reload } = useData(() => api.person(id), [id]);
  const [showDone, setShowDone] = useState(false);

  if (error) return <div className="page"><ErrorBox error={error} onRetry={reload} /></div>;
  if (!data) return <div className="page"><LoadingRows rows={10} /></div>;

  const counts = { done: 0, review: 0, in_progress: 0, waiting: 0, other: 0 };
  data.tasks.forEach((t) => (counts[bucketOf(t.sg_status_list)] += 1));
  const late = data.tasks.filter((t) => t.late).length;
  const tasks = data.tasks.filter((t) => showDone || bucketOf(t.sg_status_list) !== "done");
  const u = data.person;

  return (
    <div className="page">
      <div className="crumbs">
        <a href="#/people">Équipe</a>
        <span aria-hidden="true">/</span>
        <span>Personne</span>
      </div>
      <h1 className="display h1">{u.name}</h1>
      <div className="facts">
        {u.email && <span>{u.email}</span>}
        {u.department && <span>{linkName(u.department)}</span>}
        <span><b>{num(data.tasks.length)}</b> tâches</span>
        {data.hours_logged > 0 && <span><b>{num(data.hours_logged)} h</b> saisies</span>}
        {late > 0 && <LateChip count={late} />}
        <SgLink url={u.source_url} />
      </div>
      <StatusBar counts={counts} size="thick" />
      <div style={{ margin: "8px 0 24px" }}><Legend /></div>

      <div className="toolbar">
        <h2 className="h3" style={{ flex: 1 }}>{showDone ? "Toutes les tâches" : "Tâches ouvertes"}</h2>
        <button className="btn" aria-pressed={showDone} onClick={() => setShowDone((v) => !v)}>Inclure les terminées</button>
      </div>
      {!tasks.length ? (
        <Empty>Aucune tâche ouverte.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Tâche</th>
                <th>Production</th>
                <th className="hide-mobile">Élément</th>
                <th className="hide-mobile">Étape</th>
                <th>Statut</th>
                <th>Échéance</th>
                <th aria-label="Lien ShotGrid" />
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td>{taskName(t)}</td>
                  <td><a href={href(`/projects/${t.project?.id}`)}>{linkName(t.project)}</a></td>
                  <td className="muted hide-mobile">{linkName(t.entity)}</td>
                  <td className="muted hide-mobile">{linkName(t.step)}</td>
                  <td><Status code={t.sg_status_list} labels={labels} /></td>
                  <td>{t.late ? <LateChip days={daysLate(t.due_date)} /> : <span className="muted">{fmtDate(t.due_date, true)}</span>}</td>
                  <td><SgLink url={t.source_url} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.tasks.length >= 300 && <p className="faint small">Seules les {plural(300, "tâche", "tâches")} les plus urgentes sont affichées.</p>}
    </div>
  );
}
