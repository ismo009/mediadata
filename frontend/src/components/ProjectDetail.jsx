import React, { useState, useEffect } from "react";
import { ArrowLeft, ExternalLink, Film, CheckSquare, FileText, Box, Layers, User, Calendar, Loader2 } from "lucide-react";
import { fetchProjectDetails } from "../api";

export default function ProjectDetail({ projectId, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("Task");

  useEffect(() => {
    setLoading(true);
    fetchProjectDetails(projectId)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [projectId]);

  if (loading) {
    return (
      <div style={styles.centerContainer}>
        <Loader2 size={32} className="spin" color="var(--accent)" />
        <p style={{ marginTop: "1rem", color: "var(--text-muted)" }}>Chargement des données du projet...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={styles.centerContainer}>
        <p style={{ color: "var(--danger)" }}>Erreur : {error || "Projet introuvable"}</p>
        <button onClick={onBack} style={styles.backBtn}>
          <ArrowLeft size={16} /> Retour
        </button>
      </div>
    );
  }

  const { project, related } = data;
  const tabs = [
    { id: "Task", label: "Tâches", icon: CheckSquare, count: related.Task?.length || 0 },
    { id: "Shot", label: "Shots", icon: Film, count: related.Shot?.length || 0 },
    { id: "Note", label: "Notes", icon: FileText, count: related.Note?.length || 0 },
    { id: "Asset", label: "Assets", icon: Box, count: related.Asset?.length || 0 },
    { id: "Version", label: "Versions", icon: Layers, count: related.Version?.length || 0 },
  ];

  const currentRecords = related[activeTab] || [];

  return (
    <div style={styles.container}>
      {/* Top Banner */}
      <div style={styles.header}>
        <button onClick={onBack} style={styles.backBtn}>
          <ArrowLeft size={16} />
          <span>Tous les projets</span>
        </button>

        <div style={styles.projectHero}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.35rem" }}>
              <span className={`badge ${project.sg_status === "Active" ? "badge-active" : "badge-default"}`}>
                {project.sg_status || "Sans statut"}
              </span>
              <span style={{ fontSize: "0.8rem", color: "var(--text-sub)" }}>ID #{project.id}</span>
            </div>
            <h1 style={styles.title}>{project.name}</h1>
            <div style={styles.metaRow}>
              <div style={styles.metaItem}>
                <Calendar size={14} color="var(--text-sub)" />
                <span>{project.start_date || "—"} au {project.end_date || "—"}</span>
              </div>
            </div>
          </div>

          {project.source_url && (
            <a
              href={project.source_url}
              target="_blank"
              rel="noreferrer"
              style={styles.shotgridLinkBtn}
            >
              <span>Ouvrir dans ShotGrid</span>
              <ExternalLink size={15} />
            </a>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div style={styles.tabNav}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                ...styles.tabBtn,
                ...(isActive ? styles.tabBtnActive : {}),
              }}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
              <span style={styles.tabCount}>{tab.count}</span>
            </button>
          );
        })}
      </div>

      {/* Records List */}
      <div style={styles.recordsContainer}>
        {currentRecords.length === 0 ? (
          <div style={styles.emptyNotice}>
            Aucun enregistrement de type {activeTab} pour ce projet.
          </div>
        ) : (
          <div style={styles.recordsList}>
            {currentRecords.map((r) => {
              const name = r.name || r.code || r.cached_display_name || `#${r.id}`;
              const status = r.sg_status_list || r.sg_status;
              return (
                <div key={r.id} style={styles.recordCard}>
                  <div style={styles.recordHeader}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                      <span style={styles.recordName}>{name}</span>
                      {status && (
                        <span className={`badge ${status === "fin" || status === "apr" ? "badge-fin" : "badge-wtg"}`}>
                          {status}
                        </span>
                      )}
                    </div>
                    {r.source_url && (
                      <a
                        href={r.source_url}
                        target="_blank"
                        rel="noreferrer"
                        style={styles.recordLink}
                        title="Voir dans ShotGrid"
                      >
                        <ExternalLink size={13} />
                      </a>
                    )}
                  </div>

                  {/* Specific content depending on type */}
                  {activeTab === "Note" && (r.content || r.subject) && (
                    <div style={styles.noteContent}>
                      {r.subject && <strong style={{ display: "block", marginBottom: "0.25rem" }}>{r.subject}</strong>}
                      <p>{r.content}</p>
                    </div>
                  )}

                  {activeTab === "Task" && (
                    <div style={styles.taskMeta}>
                      {r.task_assignees && r.task_assignees.length > 0 && (
                        <div style={styles.metaBadge}>
                          <User size={12} />
                          <span>{r.task_assignees.map((u) => u.name).join(", ")}</span>
                        </div>
                      )}
                      {r.start_date && (
                        <div style={styles.metaBadge}>
                          <Calendar size={12} />
                          <span>{r.start_date} → {r.due_date || r.end_date || "—"}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    gap: "1.5rem",
  },
  centerContainer: {
    padding: "5rem 0",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
  },
  header: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: "1.5rem",
  },
  backBtn: {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.4rem",
    color: "var(--text-muted)",
    fontSize: "0.85rem",
    fontWeight: "500",
    marginBottom: "1rem",
    transition: "color 0.15s",
  },
  projectHero: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: "1rem",
  },
  title: {
    fontSize: "1.5rem",
    fontWeight: "700",
    color: "var(--text-main)",
  },
  metaRow: {
    display: "flex",
    gap: "1.25rem",
    marginTop: "0.4rem",
  },
  metaItem: {
    display: "flex",
    alignItems: "center",
    gap: "0.35rem",
    fontSize: "0.82rem",
    color: "var(--text-muted)",
  },
  shotgridLinkBtn: {
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
    padding: "0.55rem 0.9rem",
    backgroundColor: "var(--accent-soft)",
    border: "1px solid rgba(56, 189, 248, 0.3)",
    borderRadius: "var(--radius-sm)",
    color: "var(--accent)",
    fontWeight: "600",
    fontSize: "0.85rem",
    textDecoration: "none",
  },
  tabNav: {
    display: "flex",
    gap: "0.5rem",
    borderBottom: "1px solid var(--border)",
    paddingBottom: "0.5rem",
    overflowX: "auto",
  },
  tabBtn: {
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
    padding: "0.55rem 0.9rem",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-muted)",
    fontSize: "0.88rem",
    fontWeight: "500",
    transition: "all 0.15s ease",
  },
  tabBtnActive: {
    backgroundColor: "var(--bg-card)",
    color: "var(--accent)",
    fontWeight: "600",
    border: "1px solid var(--border)",
  },
  tabCount: {
    fontSize: "0.75rem",
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    padding: "0.1rem 0.4rem",
    borderRadius: "999px",
  },
  recordsContainer: {
    minHeight: "300px",
  },
  emptyNotice: {
    padding: "3rem",
    textAlign: "center",
    color: "var(--text-sub)",
    fontSize: "0.9rem",
    backgroundColor: "rgba(0, 0, 0, 0.1)",
    borderRadius: "var(--radius)",
    border: "1px dashed var(--border)",
  },
  recordsList: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
    gap: "0.85rem",
  },
  recordCard: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    padding: "0.9rem 1rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.5rem",
  },
  recordHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  recordName: {
    fontWeight: "600",
    fontSize: "0.92rem",
    color: "var(--text-main)",
  },
  recordLink: {
    color: "var(--text-muted)",
    padding: "2px",
  },
  noteContent: {
    fontSize: "0.82rem",
    color: "var(--text-muted)",
    backgroundColor: "rgba(0, 0, 0, 0.2)",
    padding: "0.6rem",
    borderRadius: "4px",
    lineHeight: "1.4",
  },
  taskMeta: {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: "0.5rem",
    marginTop: "0.2rem",
  },
  metaBadge: {
    display: "flex",
    alignItems: "center",
    gap: "0.3rem",
    fontSize: "0.75rem",
    color: "var(--text-sub)",
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    padding: "0.2rem 0.45rem",
    borderRadius: "4px",
  },
};
