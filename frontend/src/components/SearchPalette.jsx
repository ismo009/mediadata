import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { href, navigate } from "../lib";

const KIND = {
  Project: "Production", Task: "Tâche", Shot: "Plan", Sequence: "Séquence", Asset: "Asset",
  Version: "Version", Note: "Note", HumanUser: "Personne", Step: "Étape", Playlist: "Playlist",
};

function target(r) {
  if (r.entity_type === "Project") return href(`/projects/${r.entity_id}`);
  if (r.entity_type === "HumanUser") return href(`/people/${r.entity_id}`);
  if (!r.project_id) return null;
  if (r.entity_type === "Task") return href(`/projects/${r.project_id}/tasks`, { q: r.name });
  if (r.entity_type === "Shot" || r.entity_type === "Sequence") return href(`/projects/${r.project_id}/shots`);
  if (r.entity_type === "Note") return href(`/projects/${r.project_id}/notes`);
  if (r.entity_type === "Version") return href(`/projects/${r.project_id}/versions`);
  if (r.entity_type === "Asset") return href(`/projects/${r.project_id}/assets`);
  return href(`/projects/${r.project_id}`);
}

export default function SearchPalette({ onClose }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => inputRef.current?.focus(), []);
  useEffect(() => {
    if (q.trim().length < 2) {
      setResults([]);
      return undefined;
    }
    const t = setTimeout(() => api.search(q).then((d) => { setResults(d.results.filter(target)); setActive(0); }).catch(() => setResults([])), 150);
    return () => clearTimeout(t);
  }, [q]);

  const onKey = (e) => {
    if (e.key === "Escape") onClose();
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && results[active]) { navigate(target(results[active]).slice(1)); onClose(); }
  };

  return (
    <div className="palette-backdrop" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-label="Recherche" onMouseDown={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
          placeholder="Production, plan, tâche, note, personne…"
          aria-label="Rechercher"
        />
        {q.trim().length >= 2 && (
          <ul role="listbox">
            {results.length ? (
              results.map((r, i) => (
                <li key={`${r.entity_type}-${r.entity_id}`}>
                  <a href={target(r)} onClick={onClose} data-active={i === active} onMouseEnter={() => setActive(i)}>
                    <span className="kind">{KIND[r.entity_type] || r.entity_type}</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {r.name || `#${r.entity_id}`}
                      {r.project_name && r.entity_type !== "Project" && <span className="faint"> dans {r.project_name}</span>}
                    </span>
                  </a>
                </li>
              ))
            ) : (
              <li className="muted" style={{ padding: "10px 12px" }}>Aucun résultat pour « {q} ».</li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
