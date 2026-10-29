import React, { useState } from "react";
import { FolderKanban, CheckSquare, Film, FileText, Search, ExternalLink, Calendar, ArrowRight } from "lucide-react";

export default function DashboardOverview({ dashboardData, onSelectProject }) {
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const projects = dashboardData?.projects || [];

  const filteredProjects = projects.filter((p) => {
    const matchesSearch =
      (p.name || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
      (p.code || "").toLowerCase().includes(searchTerm.toLowerCase());
    const isActive = p.sg_status === "Active" || p.sg_status === "act";

    if (statusFilter === "active") return matchesSearch && isActive;
    if (statusFilter === "other") return matchesSearch && !isActive;
    return matchesSearch;
  });

  return (
    <div style={styles.container}>
      {/* KPI Metric Cards */}
      <div style={styles.kpiGrid}>
        <div style={styles.kpiCard}>
          <div style={styles.kpiIconWrap}>
            <FolderKanban size={20} color="var(--accent)" />
          </div>
          <div>
            <p style={styles.kpiLabel}>Projets Actifs</p>
            <h3 style={styles.kpiValue}>{dashboardData?.projects_active ?? "—"}</h3>
            <span style={styles.kpiSub}>sur {dashboardData?.projects_total ?? "—"} au total</span>
          </div>
        </div>

        <div style={styles.kpiCard}>
          <div style={{ ...styles.kpiIconWrap, background: "rgba(16, 185, 129, 0.12)" }}>
            <CheckSquare size={20} color="#10b981" />
          </div>
          <div>
            <p style={styles.kpiLabel}>Tâches Totales</p>
            <h3 style={styles.kpiValue}>{dashboardData?.tasks_total?.toLocaleString() ?? "—"}</h3>
            <span style={styles.kpiSub}>synchronisées en cache</span>
          </div>
        </div>

        <div style={styles.kpiCard}>
          <div style={{ ...styles.kpiIconWrap, background: "rgba(245, 158, 11, 0.12)" }}>
            <Film size={20} color="#f59e0b" />
          </div>
          <div>
            <p style={styles.kpiLabel}>Shots & Plans</p>
            <h3 style={styles.kpiValue}>{dashboardData?.shots_total?.toLocaleString() ?? "—"}</h3>
            <span style={styles.kpiSub}>en suivi de prod</span>
          </div>
        </div>

        <div style={styles.kpiCard}>
          <div style={{ ...styles.kpiIconWrap, background: "rgba(168, 85, 247, 0.12)" }}>
            <FileText size={20} color="#a855f7" />
          </div>
          <div>
            <p style={styles.kpiLabel}>Notes & Retours</p>
            <h3 style={styles.kpiValue}>{dashboardData?.notes_total?.toLocaleString() ?? "—"}</h3>
            <span style={styles.kpiSub}>indexées en FTS5</span>
          </div>
        </div>
      </div>

      {/* Projects Section */}
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Projets de Production</h2>
          <p style={styles.sectionSubtitle}>
            Sélectionnez un projet pour explorer ses shots, tâches, notes et versions associées.
          </p>
        </div>

        <div style={styles.filtersBar}>
          <div style={styles.searchWrap}>
            <Search size={15} color="var(--text-muted)" style={styles.searchIcon} />
            <input
              type="text"
              placeholder="Rechercher un projet..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={styles.searchInput}
            />
          </div>

          <div style={styles.segmentedControl}>
            <button
              onClick={() => setStatusFilter("all")}
              style={{
                ...styles.segBtn,
                ...(statusFilter === "all" ? styles.segBtnActive : {}),
              }}
            >
              Tous ({projects.length})
            </button>
            <button
              onClick={() => setStatusFilter("active")}
              style={{
                ...styles.segBtn,
                ...(statusFilter === "active" ? styles.segBtnActive : {}),
              }}
            >
              Actifs ({dashboardData?.projects_active || 0})
            </button>
          </div>
        </div>
      </div>

      {/* Projects Grid */}
      <div style={styles.projectGrid}>
        {filteredProjects.map((p) => {
          const isActive = p.sg_status === "Active" || p.sg_status === "act";
          return (
            <div
              key={p.id}
              onClick={() => onSelectProject(p.id)}
              style={styles.projectCard}
            >
              <div style={styles.cardHeader}>
                <span className={`badge ${isActive ? "badge-active" : "badge-default"}`}>
                  {p.sg_status || "Sans statut"}
                </span>
                {p.source_url && (
                  <a
                    href={p.source_url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    style={styles.externalLink}
                    title="Ouvrir dans ShotGrid"
                  >
                    <ExternalLink size={14} />
                  </a>
                )}
              </div>

              <h4 style={styles.projectTitle}>{p.name || `Projet #${p.id}`}</h4>

              <div style={styles.projectDates}>
                <Calendar size={13} color="var(--text-sub)" />
                <span>
                  {p.start_date || "—"} → {p.end_date || "—"}
                </span>
              </div>

              <div style={styles.cardFooter}>
                <span style={styles.viewDetailsText}>Explorer le projet</span>
                <ArrowRight size={14} color="var(--accent)" />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    gap: "2rem",
  },
  kpiGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
    gap: "1rem",
  },
  kpiCard: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: "1.25rem",
    display: "flex",
    alignItems: "flex-start",
    gap: "1rem",
    boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
  },
  kpiIconWrap: {
    width: "42px",
    height: "42px",
    borderRadius: "10px",
    backgroundColor: "var(--accent-soft)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  kpiLabel: {
    fontSize: "0.8rem",
    color: "var(--text-muted)",
    fontWeight: "500",
  },
  kpiValue: {
    fontSize: "1.6rem",
    fontWeight: "700",
    color: "var(--text-main)",
    letterSpacing: "-0.02em",
    lineHeight: "1.2",
    marginTop: "0.15rem",
  },
  kpiSub: {
    fontSize: "0.75rem",
    color: "var(--text-sub)",
  },
  sectionHeader: {
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: "1rem",
    borderBottom: "1px solid var(--border)",
    paddingBottom: "1rem",
  },
  sectionTitle: {
    fontSize: "1.25rem",
    fontWeight: "700",
    color: "var(--text-main)",
  },
  sectionSubtitle: {
    fontSize: "0.85rem",
    color: "var(--text-muted)",
    marginTop: "0.2rem",
  },
  filtersBar: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
  },
  searchWrap: {
    position: "relative",
    display: "flex",
    alignItems: "center",
  },
  searchIcon: {
    position: "absolute",
    left: "0.75rem",
  },
  searchInput: {
    backgroundColor: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    padding: "0.45rem 0.75rem 0.45rem 2.2rem",
    fontSize: "0.85rem",
    color: "var(--text-main)",
    outline: "none",
    width: "220px",
  },
  segmentedControl: {
    display: "flex",
    backgroundColor: "var(--bg-input)",
    borderRadius: "var(--radius-sm)",
    padding: "2px",
    border: "1px solid var(--border)",
  },
  segBtn: {
    padding: "0.35rem 0.65rem",
    fontSize: "0.78rem",
    color: "var(--text-muted)",
    borderRadius: "4px",
    fontWeight: "500",
    transition: "all 0.15s ease",
  },
  segBtnActive: {
    backgroundColor: "var(--bg-card)",
    color: "var(--text-main)",
    fontWeight: "600",
  },
  projectGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
    gap: "1rem",
  },
  projectCard: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: "1.25rem",
    cursor: "pointer",
    transition: "all 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
  },
  cardHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  externalLink: {
    color: "var(--text-muted)",
    padding: "4px",
    display: "flex",
    alignItems: "center",
    borderRadius: "4px",
    transition: "color 0.15s",
  },
  projectTitle: {
    fontSize: "1rem",
    fontWeight: "600",
    color: "var(--text-main)",
    lineHeight: "1.3",
  },
  projectDates: {
    display: "flex",
    alignItems: "center",
    gap: "0.45rem",
    fontSize: "0.78rem",
    color: "var(--text-muted)",
  },
  cardFooter: {
    marginTop: "auto",
    paddingTop: "0.75rem",
    borderTop: "1px solid rgba(255, 255, 255, 0.05)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  viewDetailsText: {
    fontSize: "0.8rem",
    color: "var(--accent)",
    fontWeight: "600",
  },
};
