import React, { useState, useEffect } from "react";
import {
  ArrowLeft,
  ExternalLink,
  Film,
  CheckSquare,
  FileText,
  Box,
  Layers,
  User,
  Calendar,
  Loader2,
  ChevronRight,
  Hash,
} from "lucide-react";
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
        <Loader2 size={36} className="spin" color="var(--accent)" />
        <p style={{ marginTop: "1rem", color: "var(--text-muted)", fontSize: "0.9rem" }}>
          Chargement de l'espace projet...
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={styles.centerContainer}>
        <p style={{ color: "var(--danger)", fontWeight: "600" }}>
          Erreur : {error || "Projet introuvable"}
        </p>
        <button onClick={onBack} style={styles.backBtn}>
          <ArrowLeft size={16} /> Revenir aux projets
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
      {/* Breadcrumb & Navigation */}
      <div style={styles.breadcrumbBar}>
        <button onClick={onBack} style={styles.backBtn}>
          <ArrowLeft size={15} />
          <span>Projets</span>
        </button>
        <ChevronRight size={14} color="var(--text-sub)" />
        <span style={styles.currentBreadcrumb}>{project.name}</span>
      </div>

      {/* Project Hero Header */}
      <div style={styles.heroCard}>
        <div style={styles.heroInfo}>
          <div style={styles.heroBadgesRow}>
            <span
              className={`badge ${project.is_active ? "badge-active" : "badge-default"}`}
            >
              {project.status_label || "Sans statut"}
            </span>
            <div style={styles.idChip}>
              <Hash size={12} color="var(--text-sub)" />
              <span>{project.id}</span>
            </div>
          </div>

          <h1 style={styles.title}>{project.name}</h1>

          <div style={styles.metaRow}>
            <div style={styles.metaItem}>
              <Calendar size={14} color="var(--text-sub)" />
              <span>
                {project.start_date || "Début indéterminé"} → {project.end_date || "En cours"}
              </span>
            </div>
          </div>
        </div>

        {project.source_url && (
          <a
            href={project.source_url}
            target="_blank"
            rel="noreferrer"
            style={styles.shotgridActionBtn}
          >
            <span>Ouvrir dans ShotGrid</span>
            <ExternalLink size={15} />
          </a>
        )}
      </div>

      {/* Modern Tabs Navigation */}
      <div style={styles.tabsContainer}>
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
              <Icon size={16} color={isActive ? "var(--accent)" : "var(--text-sub)"} />
              <span>{tab.label}</span>
              <span
                style={{
                  ...styles.tabCount,
                  ...(isActive ? styles.tabCountActive : {}),
                }}
              >
                {tab.count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Records Grid */}
      <div style={styles.recordsSection}>
        {currentRecords.length === 0 ? (
          <div style={styles.emptyContainer}>
            <p style={styles.emptyText}>
              Aucun élément de type <strong>{activeTab}</strong> rattaché à ce projet.
            </p>
          </div>
        ) : (
          <div style={styles.recordsGrid}>
            {currentRecords.map((r) => {
              const name = r.name || r.code || r.cached_display_name || `#${r.id}`;
              const status = r.sg_status_list || r.sg_status;
              const isFin = status === "fin" || status === "apr";
              return (
                <div key={r.id} style={styles.recordCard}>
                  <div style={styles.recordHeader}>
                    <span style={styles.recordTitle}>{name}</span>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      {status && (
                        <span className={`badge ${isFin ? "badge-fin" : "badge-wtg"}`}>
                          {status}
                        </span>
                      )}
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
                  </div>

                  {activeTab === "Note" && (r.content || r.subject) && (
                    <div style={styles.noteContent}>
                      {r.subject && (
                        <strong style={styles.noteSubject}>{r.subject}</strong>
                      )}
                      <p style={styles.noteBody}>{r.content}</p>
                    </div>
                  )}

                  {activeTab === "Task" && (
                    <div style={styles.taskMeta}>
                      {r.task_assignees && r.task_assignees.length > 0 && (
                        <div style={styles.metaChip}>
                          <User size={12} color="var(--text-sub)" />
                          <span>{r.task_assignees.map((u) => u.name).join(", ")}</span>
                        </div>
                      )}
                      {r.start_date && (
                        <div style={styles.metaChip}>
                          <Calendar size={12} color="var(--text-sub)" />
                          <span>
                            {r.start_date} → {r.due_date || r.end_date || "—"}
                          </span>
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
    gap: "1.75rem",
  },
  centerContainer: {
    padding: "6rem 0",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
  },
  breadcrumbBar: {
    display: "flex",
    alignItems: "center",
    gap: "0.6rem",
    fontSize: "0.85rem",
  },
  backBtn: {
    display: "flex",
    alignItems: "center",
    gap: "0.35rem",
    color: "var(--text-muted)",
    fontWeight: "500",
    transition: "color 0.15s",
  },
  currentBreadcrumb: {
    color: "var(--text-main)",
    fontWeight: "600",
  },
  heroCard: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: "1.85rem",
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: "1.5rem",
    boxShadow: "var(--shadow-card)",
  },
  heroInfo: {
    display: "flex",
    flexDirection: "column",
    gap: "0.5rem",
  },
  heroBadgesRow: {
    display: "flex",
    alignItems: "center",
    gap: "0.6rem",
  },
  idChip: {
    display: "flex",
    alignItems: "center",
    gap: "0.25rem",
    fontSize: "0.75rem",
    color: "var(--text-sub)",
    fontFamily: "'JetBrains Mono', monospace",
  },
  title: {
    fontSize: "1.75rem",
    fontWeight: "800",
    color: "var(--text-main)",
    letterSpacing: "-0.03em",
  },
  metaRow: {
    display: "flex",
    gap: "1.5rem",
    marginTop: "0.25rem",
  },
  metaItem: {
    display: "flex",
    alignItems: "center",
    gap: "0.4rem",
    fontSize: "0.82rem",
    color: "var(--text-muted)",
  },
  shotgridActionBtn: {
    display: "flex",
    alignItems: "center",
    gap: "0.55rem",
    padding: "0.65rem 1.1rem",
    backgroundColor: "var(--accent-soft)",
    border: "1px solid var(--accent-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--accent)",
    fontWeight: "600",
    fontSize: "0.85rem",
    textDecoration: "none",
    boxShadow: "0 2px 10px rgba(99, 102, 241, 0.15)",
    transition: "all 0.15s ease",
  },
  tabsContainer: {
    display: "flex",
    gap: "0.4rem",
    borderBottom: "1px solid var(--border)",
    paddingBottom: "0.4rem",
    overflowX: "auto",
  },
  tabBtn: {
    display: "flex",
    alignItems: "center",
    gap: "0.55rem",
    padding: "0.6rem 1rem",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-muted)",
    fontSize: "0.88rem",
    fontWeight: "500",
    transition: "all 0.15s ease",
  },
  tabBtnActive: {
    backgroundColor: "var(--bg-card)",
    color: "#fff",
    fontWeight: "600",
    border: "1px solid var(--border)",
    boxShadow: "var(--shadow-sm)",
  },
  tabCount: {
    fontSize: "0.72rem",
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    padding: "0.1rem 0.45rem",
    borderRadius: "var(--radius-full)",
    color: "var(--text-sub)",
    fontWeight: "600",
  },
  tabCountActive: {
    backgroundColor: "var(--accent-soft)",
    color: "var(--accent)",
  },
  recordsSection: {
    minHeight: "350px",
  },
  emptyContainer: {
    padding: "4rem 2rem",
    textAlign: "center",
    backgroundColor: "var(--bg-card)",
    borderRadius: "var(--radius)",
    border: "1px dashed var(--border)",
  },
  emptyText: {
    fontSize: "0.9rem",
    color: "var(--text-muted)",
  },
  recordsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
    gap: "1rem",
  },
  recordCard: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: "1rem 1.15rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
    boxShadow: "var(--shadow-card)",
  },
  recordHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "0.75rem",
  },
  recordTitle: {
    fontWeight: "600",
    fontSize: "0.95rem",
    color: "var(--text-main)",
  },
  recordLink: {
    color: "var(--text-sub)",
    padding: "3px",
    display: "flex",
    alignItems: "center",
    transition: "color 0.15s",
  },
  noteContent: {
    fontSize: "0.82rem",
    backgroundColor: "rgba(0, 0, 0, 0.3)",
    padding: "0.75rem",
    borderRadius: "var(--radius-sm)",
    lineHeight: "1.5",
    border: "1px solid rgba(255, 255, 255, 0.04)",
  },
  noteSubject: {
    display: "block",
    color: "var(--text-main)",
    marginBottom: "0.3rem",
    fontWeight: "600",
  },
  noteBody: {
    color: "var(--text-muted)",
    whiteSpace: "pre-wrap",
  },
  taskMeta: {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: "0.5rem",
  },
  metaChip: {
    display: "flex",
    alignItems: "center",
    gap: "0.35rem",
    fontSize: "0.75rem",
    color: "var(--text-muted)",
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    padding: "0.25rem 0.55rem",
    borderRadius: "6px",
    border: "1px solid var(--border)",
  },
};
