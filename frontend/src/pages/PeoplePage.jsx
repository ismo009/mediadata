import React, { useState } from "react";
import { Search } from "lucide-react";
import { api } from "../api";
import { href, num, useData } from "../lib";
import { Empty, ErrorBox, LateChip, LoadingRows } from "../components/ui";

export default function PeoplePage() {
  const { data, error, reload } = useData(() => api.people(), []);
  const [filter, setFilter] = useState("");
  const [onlyBusy, setOnlyBusy] = useState(true);

  if (error) return <div className="page"><ErrorBox error={error} onRetry={reload} /></div>;
  const people = (data?.people || [])
    .filter((p) => p.active)
    .filter((p) => (onlyBusy ? p.open > 0 : true))
    .filter((p) => !filter || p.name.toLowerCase().includes(filter.toLowerCase()));
  const maxOpen = Math.max(1, ...people.map((p) => p.open));

  return (
    <div className="page">
      <h1 className="display h1" style={{ marginBottom: 6 }}>Équipe</h1>
      <p className="lede">Charge de travail ouverte par personne, toutes productions confondues.</p>
      <div className="toolbar">
        <div className="search-field grow">
          <Search size={14} />
          <input className="input" placeholder="Rechercher une personne…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Rechercher une personne" />
        </div>
        <div className="segmented" role="group" aria-label="Personnes affichées">
          <button aria-pressed={onlyBusy} onClick={() => setOnlyBusy(true)}>Avec des tâches ouvertes</button>
          <button aria-pressed={!onlyBusy} onClick={() => setOnlyBusy(false)}>Tout le monde</button>
        </div>
      </div>
      {!data ? (
        <LoadingRows rows={10} />
      ) : !people.length ? (
        <Empty>Personne ne correspond.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Personne</th>
                <th style={{ width: "38%" }}>Tâches ouvertes</th>
                <th className="num">En review</th>
                <th className="num">Retard</th>
                <th className="num hide-mobile">Productions</th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.id}>
                  <td>
                    <a href={href(`/people/${p.id}`)} style={{ fontWeight: 550 }}>{p.name}</a>
                    {p.department && <div className="faint small">{p.department}</div>}
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div className="sbar" style={{ width: `${(p.open / maxOpen) * 100}%`, minWidth: p.open ? 4 : 0 }}>
                        {p.open > 0 && <div className="seg in_progress" style={{ flexGrow: 1 }} />}
                      </div>
                      <span className="small">{num(p.open)}</span>
                    </div>
                  </td>
                  <td className="num">{p.review ? num(p.review) : <span className="faint">0</span>}</td>
                  <td className="num">{p.late ? <LateChip count={p.late} compact /> : <span className="faint">0</span>}</td>
                  <td className="num hide-mobile">{num(p.projects)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
