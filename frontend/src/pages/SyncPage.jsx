import React, { useState } from "react";
import { CheckCircle2, AlertTriangle } from "lucide-react";
import { api } from "../api";
import { useApp } from "../App";
import { fmtDate, num, relTime, useData } from "../lib";
import { ErrorBox, LoadingRows } from "../components/ui";

const MODE_LABEL = { full: "Complète", incremental: "Incrémentale", auto: "Automatique" };
const STATUS_LABEL = { completed: "Terminée", failed: "Échouée", running: "En cours" };

function duration(a, b) {
  if (!a || !b) return "";
  const s = Math.round((new Date(b) - new Date(a)) / 1000);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}

export default function SyncPage() {
  const { sync, startSync } = useApp();
  const runs = useData(() => api.syncRuns(), [sync?.status]);
  const types = useData(() => api.entityTypes(), [sync?.status]);
  const [audit, setAudit] = useState(null);
  const [auditing, setAuditing] = useState(false);
  const [auditError, setAuditError] = useState(null);
  const running = sync?.status === "running";

  const runAudit = async () => {
    setAuditing(true);
    setAuditError(null);
    try {
      setAudit(await api.syncAudit(true));
    } catch (e) {
      setAuditError(e);
    } finally {
      setAuditing(false);
    }
  };

  return (
    <div className="page">
      <h1 className="display h1" style={{ marginBottom: 6 }}>Synchronisation</h1>
      <p className="lede">
        Les données affichées viennent d'une copie locale de ShotGrid. Une synchronisation incrémentale récupère seulement ce qui a changé ;
        une synchronisation complète revérifie chaque enregistrement et retire ceux supprimés dans ShotGrid.
      </p>

      <div className="toolbar">
        <button className="btn primary" disabled={running} onClick={() => startSync("incremental")}>Synchroniser les changements</button>
        <button className="btn" disabled={running} onClick={() => startSync("full")}>Synchronisation complète</button>
        <button className="btn" disabled={auditing} onClick={runAudit}>{auditing ? "Comparaison en cours…" : "Comparer avec ShotGrid"}</button>
        {running && <span className="muted small">Synchronisation en cours, {num(sync.records_count)} enregistrements traités</span>}
      </div>

      {auditError && <ErrorBox error={auditError} />}
      {audit && <AuditResult audit={audit} />}

      <div className="grid-2" style={{ marginTop: 24 }}>
        <section className="section">
          <h2 className="h3" style={{ marginBottom: 10 }}>Historique</h2>
          {!runs.data ? (
            <LoadingRows />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr><th>Début</th><th>Type</th><th>Résultat</th><th className="num">Enregistrements</th><th className="num hide-mobile">Durée</th></tr>
                </thead>
                <tbody>
                  {runs.data.runs.map((r) => (
                    <tr key={r.id} title={r.error || ""}>
                      <td>{fmtDate(r.started_at)}, {new Date(r.started_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</td>
                      <td>{MODE_LABEL[r.mode] || r.mode}</td>
                      <td className={r.status === "failed" ? "late-text" : ""}>{STATUS_LABEL[r.status] || r.status}</td>
                      <td className="num">{num(r.records_count)}</td>
                      <td className="num hide-mobile">{duration(r.started_at, r.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section className="section">
          <h2 className="h3" style={{ marginBottom: 10 }}>Données synchronisées</h2>
          {!types.data ? (
            <LoadingRows />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr><th>Type</th><th className="num">Enregistrements</th><th className="hide-mobile">Mis à jour</th></tr>
                </thead>
                <tbody>
                  {types.data.entity_types.map((t) => (
                    <tr key={t.entity_type}>
                      <td>{t.display_name}{t.display_name !== t.entity_type && <span className="faint small"> {t.entity_type}</span>}</td>
                      <td className="num">{num(t.record_count)}</td>
                      <td className="muted hide-mobile">{relTime(t.last_synced_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function AuditResult({ audit }) {
  const gaps = audit.entities.filter((e) => !e.in_sync);
  return (
    <section className="section" style={{ marginTop: 16 }}>
      <h2 className="h3" style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
        {audit.in_sync ? <CheckCircle2 size={18} className="ok" /> : <AlertTriangle size={18} className="late-text" />}
        {audit.in_sync ? "La copie locale correspond exactement à ShotGrid" : `${gaps.length} type(s) avec des écarts`}
      </h2>
      {gaps.length > 0 && (
        <div className="table-wrap" style={{ marginBottom: 14 }}>
          <table className="data">
            <thead><tr><th>Type</th><th className="num">ShotGrid</th><th className="num">Local</th><th className="num">Manquants</th><th className="num">Supprimés dans ShotGrid</th></tr></thead>
            <tbody>
              {gaps.map((e) => (
                <tr key={e.entity_type}>
                  <td>{e.display_name}</td><td className="num">{num(e.live)}</td><td className="num">{num(e.local)}</td>
                  <td className="num">{num(e.missing_locally)}</td><td className="num">{num(e.deleted_in_shotgrid)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        Index de recherche : {audit.search_index.healthy ? "cohérent" : `incohérent (${num(audit.search_index.fts_rows)} lignes pour ${num(audit.search_index.records)} enregistrements)`}.
        {audit.unsynced_entity_types?.length
          ? ` Types présents dans ShotGrid mais non synchronisés : ${audit.unsynced_entity_types.map((t) => `${t.display_name} (${t.live})`).join(", ")}.`
          : " Tous les types de données ShotGrid utiles sont synchronisés."}
      </p>
    </section>
  );
}
