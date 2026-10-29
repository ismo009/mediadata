import React, { useState } from "react";
import {
  FolderKanban,
  CheckSquare,
  Film,
  FileText,
  Search,
  ExternalLink,
  Calendar,
  ArrowUpRight,
  TrendingUp,
} from "lucide-react";

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

  // Color generator for project avatars
  const getGradientForProject = (name = "") => {
    const gradients = [
      "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)",
      "linear-gradient(135deg, #0284c7 0%, #06b6d4 100%)",
      "linear-gradient(135deg, #059669 0%, #10b981 100%)",
      "linear-gradient(135deg, #d97706 0%, #f59e0b 100%)",
      "linear-gradient(135deg, #e11d48 0%, #f43f5e 100%)",
    ];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return gradients[Math.abs(hash) % gradients.length];
  };

  return (
    <div style={styles.container}>
      {/* KPI Section */}
      <div style={styles.kpiGrid}>
        <div style={styles.kpiCard}>
          <div style={styles.kpiTopRow}>
            <div style={{ ...styles.kpiIconWrap, background: "rgba(99, 102, 241, 0.12)" }}>
              <FolderKanban size={20} color="#818cf8" />
            </div>
            <span style={styles.kpiBadge}>
              <TrendingUp size={12} color="#10b981" />
              <span>Studio Live</span>
            </span>
          </div>
          <div style={styles.kpiContent}>
            <span style={styles.kpiLabel}>Projets en Production</span>
            <div style={styles.kpiValueRow}>
              <h3 style={styles.kpiValue}>{dashboardData?.projects_active ?? "—"}</h3>
              <span style={styles.kpiSub}>/ {dashboardData?.projects_total ?? "—"} total</span>
            </div>
          </div>
        </div>

        <div style={styles.kpiCard}>
          <div style={styles.kpiTopRow}>
            <div style={{ ...styles.kpiIconWrap, background: "rgba(16, 185, 129, 0.12)" }}>
              <CheckSquare size={20} color="#34d399" />
            </div>
            <span style={{ ...styles.kpiBadge, color: "#34d399" }}>Synchronisé</span>
          </div>
          <div style={styles.kpiContent}>
            <span style={styles.kpiLabel}>Tâches Assignées</span>
            <div style={styles.kpiValueRow}>
              <h3 style={styles.kpiValue}>
                {dashboardData?.tasks_total?.toLocaleString() ?? "—"}
              </h3>
            </div>
          </div>
        </div>

        <div style={styles.kpiCard}>
          <div style={styles.kpiTopRow}>
            <div style={{ ...styles.kpiIconWrap, background: "rgba(245, 158, 11, 0.12)" }}>
              <Film size={20} color="#fbbf24" />
            </div>
            <span style={{ ...styles.kpiBadge, color: "#fbbf24" }}>VFX & 3D</span>
          </div>
          <div style={styles.kpiContent}>
            <span style={styles.kpiLabel}>Shots & Plans</span>
            <div style={styles.kpiValueRow}>
              <h3 style={styles.kpiValue}>
                {dashboardData?.shots_total?.toLocaleString() ?? "—"}
              </h3>
            </div>
          </div>
        </div>

        <div style={styles.kpiCard}>
          <div style={styles.kpiTopRow}>
            <div style={{ ...styles.kpiIconWrap, background: "rgba(168, 85, 247, 0.12)" }}>
              <FileText size={20} color="#c084fc" />
            </div>
            <span style={{ ...styles.kpiBadge, color: "#c084fc" }}>Index FTS5</span>
          </div>
          <div style={styles.kpiContent}>
            <span style={styles.kpiLabel}>Notes & Retours</span>
            <div style={styles.kpiValueRow}>
              <h3 style={styles.kpiValue}>
                {dashboardData?.notes_total?.toLocaleString() ?? "—"}
              </h3>
            </div>
          </div>
        </div>
      </div>

      {/* Main Section Header */}
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Catalogue des Projets</h2>
          <p style={styles.sectionSubtitle}>
            Sélectionnez un projet pour consulter ses dépendances, tâches et retours artistiques.
          </p>
        </div>

        <div style={styles.filtersBar}>
          <div style={styles.searchWrap}>
            <Search size={15} color="var(--text-sub)" style={styles.searchIcon} />
            <input
              type="text"
              placeholder="Rechercher par nom ou code..."
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
          const initial = (p.name || "P").charAt(0).toUpperCase();
          const avatarGradient = getGradientForProject(p.name || "");

          return (
            <div
              key={p.id}
              onClick={() => onSelectProject(p.id)}
              style={styles.projectCard}
            >
              <div style={styles.cardHeader}>
                <div style={{ ...styles.projectAvatar, background: avatarGradient }}>
                  <span>{initial}</span>
                </div>
                <div style={styles.headerRight}>
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
                      <ExternalLink size={13} />
                    </a>
                  )}
                </div>
              </div>

              <div style={styles.cardBody}>
                <h4 style={styles.projectTitle}>{p.name || `Projet #${p.id}`}</h4>
                <div style={styles.projectMeta}>
                  <Calendar size={13} color="var(--text-sub)" />
                  <span>
                    {p.start_date || "Non défini"} → {p.end_date || "En cours"}
                  </span>
                </div>
              </div>

              <div style={styles.cardFooter}>
                <span style={styles.viewLinkText}>Ouvrir l'espace projet</span>
                <div style={styles.arrowCircle}>
                  <ArrowUpRight size={13} color="#fff" />
                </div>
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
    gap: "2.25rem",
  },
  kpiGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
    gap: "1.25rem",
  },
  kpiCard: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: "1.4rem",
    display: "flex",
    flexDirection: "column",
    gap: "1.2rem",
    boxShadow: "var(--shadow-card)",
    position: "relative",
    overflow: "hidden",
  },
  kpiTopRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  kpiIconWrap: {
    width: "40px",
    height: "40px",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  kpiBadge: {
    display: "flex",
    alignItems: "center",
    gap: "0.3rem",
    fontSize: "0.72rem",
    fontWeight: "600",
    color: "#818cf8",
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    padding: "0.2rem 0.5rem",
    borderRadius: "var(--radius-full)",
    border: "1px solid var(--border)",
  },
  kpiContent: {
    display: "flex",
    flexDirection: "column",
    gap: "0.25rem",
  },
  kpiLabel: {
    fontSize: "0.82rem",
    color: "var(--text-muted)",
    fontWeight: "500",
  },
  kpiValueRow: {
    display: "flex",
    alignItems: "baseline",
    gap: "0.5rem",
  },
  kpiValue: {
    fontSize: "1.85rem",
    fontWeight: "800",
    color: "var(--text-main)",
    letterSpacing: "-0.03em",
    lineHeight: "1.1",
  },
  kpiSub: {
    fontSize: "0.78rem",
    color: "var(--text-sub)",
    fontWeight: "500",
  },
  sectionHeader: {
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: "1.25rem",
    paddingBottom: "0.5rem",
  },
  sectionTitle: {
    fontSize: "1.35rem",
    fontWeight: "700",
    color: "var(--text-main)",
    letterSpacing: "-0.02em",
  },
  sectionSubtitle: {
    fontSize: "0.85rem",
    color: "var(--text-muted)",
    marginTop: "0.25rem",
  },
  filtersBar: {
    display: "flex",
    alignItems: "center",
    gap: "0.85rem",
  },
  searchWrap: {
    position: "relative",
    display: "flex",
    alignItems: "center",
  },
  searchIcon: {
    position: "absolute",
    left: "0.85rem",
  },
  searchInput: {
    backgroundColor: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    padding: "0.55rem 0.85rem 0.55rem 2.4rem",
    fontSize: "0.85rem",
    color: "var(--text-main)",
    outline: "none",
    width: "250px",
    transition: "all 0.15s ease",
  },
  segmentedControl: {
    display: "flex",
    backgroundColor: "var(--bg-input)",
    borderRadius: "var(--radius-sm)",
    padding: "3px",
    border: "1px solid var(--border)",
  },
  segBtn: {
    padding: "0.4rem 0.8rem",
    fontSize: "0.8rem",
    color: "var(--text-muted)",
    borderRadius: "6px",
    fontWeight: "500",
    transition: "all 0.15s ease",
  },
  segBtnActive: {
    backgroundColor: "var(--bg-elevated)",
    color: "#fff",
    fontWeight: "600",
    boxShadow: "0 1px 4px rgba(0, 0, 0, 0.4)",
  },
  projectGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))",
    gap: "1.25rem",
  },
  projectCard: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: "1.35rem",
    cursor: "pointer",
    transition: "all 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
    boxShadow: "var(--shadow-card)",
  },
  cardHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  projectAvatar: {
    width: "38px",
    height: "38px",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#fff",
    fontWeight: "700",
    fontSize: "0.95rem",
    boxShadow: "0 2px 8px rgba(0, 0, 0, 0.3)",
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
  },
  externalLink: {
    color: "var(--text-sub)",
    padding: "5px",
    display: "flex",
    alignItems: "center",
    borderRadius: "6px",
    border: "1px solid transparent",
    transition: "all 0.15s",
  },
  cardBody: {
    display: "flex",
    flexDirection: "column",
    gap: "0.4rem",
  },
  projectTitle: {
    fontSize: "1.05rem",
    fontWeight: "700",
    color: "var(--text-main)",
    letterSpacing: "-0.01em",
    lineHeight: "1.3",
  },
  projectMeta: {
    display: "flex",
    alignItems: "center",
    gap: "0.45rem",
    fontSize: "0.78rem",
    color: "var(--text-sub)",
  },
  cardFooter: {
    marginTop: "auto",
    paddingTop: "0.85rem",
    borderTop: "1px solid rgba(255, 255, 255, 0.04)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  viewLinkText: {
    fontSize: "0.82rem",
    color: "var(--accent)",
    fontWeight: "600",
  },
  arrowCircle: {
    width: "24px",
    height: "24px",
    borderRadius: "50%",
    backgroundColor: "rgba(99, 102, 241, 0.15)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
};
