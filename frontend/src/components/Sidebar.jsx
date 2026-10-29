import React from "react";
import {
  LayoutDashboard,
  FolderKanban,
  Film,
  CheckSquare,
  Box,
  Layers,
  FileText,
  RefreshCw,
  Sparkles,
  ExternalLink,
} from "lucide-react";

const NAV_ITEMS = [
  { id: "overview", label: "Vue d'ensemble", icon: LayoutDashboard },
  { id: "projects", label: "Projets", icon: FolderKanban, entity: "projects" },
  { id: "shots", label: "Shots", icon: Film, entity: "shots" },
  { id: "tasks", label: "Tâches", icon: CheckSquare, entity: "tasks" },
  { id: "assets", label: "Assets", icon: Box, entity: "assets" },
  { id: "versions", label: "Versions", icon: Layers, entity: "versions" },
  { id: "notes", label: "Notes", icon: FileText, entity: "notes" },
];

export default function Sidebar({
  activeTab,
  onSelectTab,
  syncStatus,
  onTriggerSync,
  isSyncing,
  chatOpen,
  onToggleChat,
}) {
  return (
    <aside style={styles.sidebar}>
      <div style={styles.brandContainer}>
        <div style={styles.logoMark}>SO</div>
        <div>
          <h1 style={styles.brandTitle}>Studio Ops</h1>
          <p style={styles.brandSubtitle}>Production Hub</p>
        </div>
      </div>

      <nav style={styles.nav}>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id, item.entity)}
              style={{
                ...styles.navButton,
                ...(isActive ? styles.navButtonActive : {}),
              }}
            >
              <Icon size={18} style={isActive ? { color: "var(--accent)" } : { color: "var(--text-muted)" }} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div style={styles.footer}>
        <button
          onClick={onToggleChat}
          style={{
            ...styles.chatToggleButton,
            ...(chatOpen ? styles.chatToggleActive : {}),
          }}
        >
          <Sparkles size={16} />
          <span>Assistant IA</span>
        </button>

        <div style={styles.syncBox}>
          <div style={styles.syncHeader}>
            <span style={styles.syncLabel}>ShotGrid Sync</span>
            <button
              onClick={onTriggerSync}
              disabled={isSyncing}
              style={styles.syncButton}
              title="Lancer une synchronisation ShotGrid"
            >
              <RefreshCw size={14} className={isSyncing ? "spin" : ""} />
            </button>
          </div>
          <p style={styles.syncText}>
            {syncStatus
              ? `${syncStatus.records_count || 0} enregistrements`
              : "Aucune sync"}
          </p>
        </div>
      </div>
    </aside>
  );
}

const styles = {
  sidebar: {
    width: "240px",
    backgroundColor: "var(--bg-sidebar)",
    borderRight: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    padding: "1.25rem 0.85rem",
    userSelect: "none",
  },
  brandContainer: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    padding: "0.5rem 0.6rem 1.5rem",
    borderBottom: "1px solid var(--border)",
  },
  logoMark: {
    width: "34px",
    height: "34px",
    borderRadius: "8px",
    background: "linear-gradient(135deg, #0284c7, #38bdf8)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: "700",
    fontSize: "0.9rem",
    letterSpacing: "-0.02em",
    boxShadow: "0 4px 12px rgba(56, 189, 248, 0.25)",
  },
  brandTitle: {
    fontSize: "0.95rem",
    fontWeight: "700",
    color: "var(--text-main)",
    letterSpacing: "-0.01em",
  },
  brandSubtitle: {
    fontSize: "0.75rem",
    color: "var(--text-muted)",
  },
  nav: {
    display: "flex",
    flexDirection: "column",
    gap: "0.25rem",
    marginTop: "1.25rem",
    flex: 1,
  },
  navButton: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    padding: "0.6rem 0.75rem",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-muted)",
    fontWeight: "500",
    fontSize: "0.88rem",
    transition: "all 0.15s ease",
    textAlign: "left",
  },
  navButtonActive: {
    backgroundColor: "var(--accent-soft)",
    color: "var(--accent)",
    fontWeight: "600",
  },
  footer: {
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
    paddingTop: "1rem",
    borderTop: "1px solid var(--border)",
  },
  chatToggleButton: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "0.5rem",
    padding: "0.6rem",
    borderRadius: "var(--radius-sm)",
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    color: "var(--text-main)",
    fontWeight: "600",
    fontSize: "0.85rem",
    transition: "all 0.15s ease",
  },
  chatToggleActive: {
    background: "var(--accent-soft)",
    borderColor: "var(--accent)",
    color: "var(--accent)",
  },
  syncBox: {
    padding: "0.75rem",
    backgroundColor: "rgba(0, 0, 0, 0.2)",
    borderRadius: "var(--radius-sm)",
    border: "1px solid var(--border)",
  },
  syncHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  syncLabel: {
    fontSize: "0.75rem",
    fontWeight: "600",
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  syncButton: {
    color: "var(--text-muted)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "0.2rem",
    borderRadius: "4px",
    transition: "color 0.15s",
  },
  syncText: {
    fontSize: "0.75rem",
    color: "var(--text-sub)",
    marginTop: "0.3rem",
  },
};
