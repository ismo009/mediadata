import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ArrowUp, Square, Trash2, X } from "lucide-react";
import { api, streamChat } from "../api";
import { useApp } from "../App";
import { num } from "../lib";

const KIND = { Project: "Production", Task: "Tâche", Shot: "Plan", Sequence: "Séquence", Asset: "Asset",
  Version: "Version", Note: "Note", HumanUser: "Personne", TimeLog: "Temps", Playlist: "Playlist" };

function suggestionsFor(projectName) {
  if (projectName) {
    return [
      `Où en est ${projectName} ?`,
      `Quelles tâches sont en retard sur ${projectName} ?`,
      `Quelles tâches sont bloquées sur ${projectName} ?`,
      `Résume les dernières notes de ${projectName}`,
    ];
  }
  return [
    "Quels sont les projets actifs ?",
    "Combien de tâches sont en retard, par production ?",
    "Quelles tâches attendent une validation ?",
    "Qui a le plus de tâches ouvertes ?",
  ];
}

function loadHistory() {
  try {
    return JSON.parse(sessionStorage.getItem("lia-history") || "[]");
  } catch {
    return [];
  }
}

export default function Assistant({ projectId, onClose }) {
  const { projectName } = useApp();
  const [messages, setMessages] = useState(loadHistory);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [models, setModels] = useState({ models: [], default: "" });
  const [model, setModel] = useState("");
  const controllerRef = useRef(null);
  const logRef = useRef(null);
  const name = projectId ? projectName(projectId) : null;

  useEffect(() => {
    api.models().then((m) => {
      setModels(m);
      setModel((cur) => cur || m.default || m.models[0] || "");
    });
  }, []);

  useEffect(() => {
    try {
      sessionStorage.setItem("lia-history", JSON.stringify(messages.slice(-30).map(({ sources, ...m }) => m)));
    } catch {
      /* storage unavailable */
    }
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const update = (fn) => setMessages((ms) => {
    const copy = ms.slice();
    copy[copy.length - 1] = fn(copy[copy.length - 1]);
    return copy;
  });

  const ask = (question) => {
    const q = question.trim();
    if (!q || busy) return;
    const history = messages.filter((m) => !m.error).map(({ role, content }) => ({ role, content }));
    setMessages((ms) => [...ms, { role: "user", content: q }, { role: "assistant", content: "", streaming: true }]);
    setInput("");
    setBusy(true);
    controllerRef.current = streamChat({
      question: q,
      history,
      model,
      onSources: (sources) => update((m) => ({ ...m, sources })),
      onToken: (t) => update((m) => ({ ...m, content: m.content + t })),
      onError: (e) => update((m) => ({ ...m, content: m.content || `Lia n'a pas pu répondre : ${e.message}`, error: true })),
      onDone: () => {
        update((m) => ({ ...m, streaming: false }));
        setBusy(false);
      },
    });
  };

  const stop = () => {
    controllerRef.current?.abort();
    update((m) => ({ ...m, streaming: false }));
    setBusy(false);
  };

  return (
    <aside className="assistant" aria-label="Assistante Lia">
      <div className="assistant-head">
        <span className="title">Lia</span>
        <span className="faint small" style={{ flex: 1 }}>{name ? `Contexte : ${name}` : "Toutes les productions"}</span>
        {messages.length > 0 && (
          <button className="btn icon ghost" onClick={() => setMessages([])} disabled={busy} aria-label="Effacer la conversation" title="Effacer la conversation">
            <Trash2 size={15} />
          </button>
        )}
        <button className="btn icon ghost" onClick={onClose} aria-label="Fermer Lia">
          <X size={16} />
        </button>
      </div>

      <div className="assistant-log" ref={logRef} aria-live="polite">
        {messages.length === 0 && (
          <div style={{ display: "grid", gap: 14 }}>
            <p className="muted" style={{ margin: 0 }}>
              Posez une question sur les productions. Lia répond à partir de la copie locale de ShotGrid et cite ses sources.
            </p>
            <div className="suggestions">
              {suggestionsFor(name).map((s) => (
                <button key={s} onClick={() => ask(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="msg-user">{m.content}</div>
          ) : (
            <div key={i} className="msg-bot">
              <div className={`md ${m.error ? "late-text" : ""}`}>
                {m.content ? (
                  <ReactMarkdown components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}>{m.content}</ReactMarkdown>
                ) : (
                  m.streaming && <span className="muted">Recherche dans les données…</span>
                )}
                {m.streaming && m.content && <span className="cursor" aria-hidden="true" />}
              </div>
              {m.sources && <Sources sources={m.sources} />}
            </div>
          )
        )}
      </div>

      <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
        <textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(input);
            }
          }}
          placeholder={name ? `Une question sur ${name} ?` : "Une question sur vos productions ?"}
          aria-label="Question pour Lia"
        />
        <div className="composer-row">
          <select className="select" value={model} onChange={(e) => setModel(e.target.value)} aria-label="Modèle" disabled={!models.models.length}>
            {models.models.length ? models.models.map((m) => <option key={m} value={m}>{m}</option>) : <option>Ollama indisponible</option>}
          </select>
          {busy ? (
            <button type="button" className="btn" onClick={stop}><Square size={13} /> Arrêter</button>
          ) : (
            <button type="submit" className="btn primary" disabled={!input.trim()}><ArrowUp size={15} /> Envoyer</button>
          )}
        </div>
      </form>
    </aside>
  );
}

function Sources({ sources }) {
  const records = sources.shotgrid || [];
  const drive = sources.google_drive || [];
  const stats = sources.stats;
  const total = stats?.total ?? stats?.taches?.total;
  return (
    <details className="sources">
      <summary>
        {records.length + drive.length} sources consultées
        {total != null && <span className="faint">, {num(total)} correspondances dans la base</span>}
      </summary>
      <p style={{ margin: "6px 0 0" }} className="faint">Périmètre : {sources.scope}</p>
      <ul>
        {records.map((r) => (
          <li key={`${r.type}-${r.id}`}>
            <span className="kind">{KIND[r.type] || r.type}</span>
            {r.source_url ? <a href={r.source_url} target="_blank" rel="noreferrer">{r.name || `#${r.id}`}</a> : r.name}
          </li>
        ))}
        {drive.map((f) => (
          <li key={f.id}>
            <span className="kind">Drive</span>
            <a href={f.webViewLink} target="_blank" rel="noreferrer">{f.name}</a>
          </li>
        ))}
      </ul>
    </details>
  );
}
