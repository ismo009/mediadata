import React, { useEffect, useState } from "react";
import { AlertTriangle, ExternalLink, ImageOff } from "lucide-react";
import { fetchThumbnail } from "../api";
import { BUCKETS, bucketOf, num, plural } from "../lib";

const BUCKET_LABEL = Object.fromEntries(BUCKETS.map((b) => [b.key, b.label]));

/* Stacked status bar: one segment per bucket, hover tooltip, accessible summary. */
export function StatusBar({ counts, size = "", unit = "tâche", units = "tâches" }) {
  const [tip, setTip] = useState(null);
  const total = BUCKETS.reduce((s, b) => s + (counts?.[b.key] || 0), 0);
  if (!total) return <div className={`sbar empty ${size}`} aria-label={`Aucune ${unit}`} />;
  const summary = BUCKETS.filter((b) => counts[b.key])
    .map((b) => `${BUCKET_LABEL[b.key]} : ${num(counts[b.key])}`)
    .join(", ");
  return (
    <>
      <div className={`sbar ${size}`} role="img" aria-label={`${plural(total, unit, units)} — ${summary}`}>
        {BUCKETS.filter((b) => counts[b.key]).map((b) => {
          const n = counts[b.key];
          return (
            <div
              key={b.key}
              className={`seg ${b.key}`}
              style={{ flexGrow: n }}
              onMouseMove={(e) =>
                setTip({ x: e.clientX, y: e.clientY, text: `${BUCKET_LABEL[b.key]} · ${num(n)} (${Math.round((n / total) * 100)} %)` })
              }
              onMouseLeave={() => setTip(null)}
            />
          );
        })}
      </div>
      {tip && (
        <div className="tooltip" style={{ left: tip.x, top: tip.y }}>
          {tip.text}
        </div>
      )}
    </>
  );
}

export function Legend({ keys = ["done", "review", "in_progress", "waiting", "other"] }) {
  return (
    <div className="legend" aria-hidden="true">
      {keys.map((k) => (
        <span key={k}>
          <i className={`dot ${k}`} />
          {BUCKET_LABEL[k]}
        </span>
      ))}
    </div>
  );
}

export function Status({ code, labels }) {
  if (!code) return <span className="status faint">Sans statut</span>;
  const name = labels?.[code]?.name;
  return (
    <span className="status" title={code}>
      <i className={`dot ${bucketOf(code)}`} />
      {name || code}
      {name && name.toLowerCase() !== code && <span className="code">{code}</span>}
    </span>
  );
}

export function LateChip({ count, days, compact = false }) {
  if (!count && !days) return null;
  return (
    <span className="late-chip" title="Échéance dépassée, tâche non terminée">
      <AlertTriangle size={13} aria-hidden="true" />
      {days ? `${days} j de retard` : compact ? num(count) : `${num(count)} en retard`}
    </span>
  );
}

export function SgLink({ url, label = "Ouvrir dans ShotGrid" }) {
  if (!url) return null;
  return (
    <a className="ext" href={url} target="_blank" rel="noreferrer" title={label} aria-label={label}>
      <ExternalLink size={14} />
    </a>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="error-box" role="alert">
      {String(error?.message || error)}
      {onRetry && (
        <>
          {" "}
          <button className="btn ghost" onClick={onRetry}>
            Réessayer
          </button>
        </>
      )}
    </div>
  );
}

export function Skeleton({ h = 14, w = "100%", style }) {
  return <div className="skeleton" style={{ height: h, width: w, ...style }} />;
}

export function LoadingRows({ rows = 6 }) {
  return (
    <div style={{ display: "grid", gap: 14 }} aria-busy="true" aria-label="Chargement">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} h={18} w={`${90 - (i % 3) * 12}%`} />
      ))}
    </div>
  );
}

/* Thumbnail fetched fresh from ShotGrid (stored URLs expire). */
export function Thumb({ entityType, id, alt }) {
  const [url, setUrl] = useState(undefined);
  useEffect(() => {
    let alive = true;
    fetchThumbnail(entityType, id).then((u) => alive && setUrl(u));
    return () => {
      alive = false;
    };
  }, [entityType, id]);
  return (
    <div className="thumb">
      {url === undefined ? (
        <div className="skeleton" style={{ width: "100%", height: "100%" }} />
      ) : url ? (
        <img src={url} alt={alt || ""} loading="lazy" onError={() => setUrl(null)} />
      ) : (
        <ImageOff size={20} aria-label="Pas d'aperçu" />
      )}
    </div>
  );
}
