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
  ChevronRight,
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
      {/* Brand Header */}
      <div style={styles.brandContainer}>
        <div style={styles.logoMark}>
          <span style={styles.logoText}>SO</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <h1 style={styles.brandTitle}>Studio Ops</h1>
          <span style={styles.brandSubtitle}>Production Hub</span>
        </div>
      </div>

      {/* Navigation */}
      <div style={styles.navSection}>
        <span style={styles.sectionLabel}>Supervision</span>
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
                <div style={styles.navIconWrap}>
                  <Icon
                    size={18}
                    style={isActive ? { color: "var(--accent)" } : { color: "var(--text-sub)" }}
                  />
                </div>
                <span style={styles.navLabel}>{item.label}</span>
                {isActive && <div style={styles.activePillIndicator} />}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Footer & Tools */}
      <div style={styles.footer}>
        {/* AI Assistant Toggle Button */}
        <button
          onClick={onToggleChat}
          style={{
            ...styles.chatToggleButton,
            ...(chatOpen ? styles.chatToggleActive : {}),
          }}
        >
          <div style={styles.chatIconWrap}>
            <Sparkles size={15} color={chatOpen ? "#fff" : "var(--accent)"} />
          </div>
          <span style={{ flex: 1, textAlign: "left" }}>Assistant IA</span>
          <ChevronRight size={14} style={{ opacity: 0.6 }} />
        </button>

        {/* ShotGrid Sync Widget */}
        <div style={styles.syncCard}>
          <div style={styles.syncHeader}>
            <div style={styles.syncIndicator}>
              <span style={{
                ...styles.syncDot,
                backgroundColor: isSyncing ? "var(--warning)" : "var(--success)",
                boxShadow: isSyncing ? "0 0 8px rgba(245, 158, 11, 0.6)" : "0 0 8px rgba(16, 185, 129, 0.6)",
              }} />
              <span style={styles.syncTitle}>ShotGrid Cache</span>
            </div>
            <button
              onClick={onTriggerSync}
              disabled={isSyncing}
              style={{
                ...styles.syncBtn,
                ...(isSyncing ? { opacity: 0.6, cursor: "not-allowed" } : {}),
              }}
              title="Lancer une synchronisation ShotGrid"
            >
              <RefreshCw size={13} className={isSyncing ? "spin" : ""} color="var(--text-muted)" />
            </button>
          </div>
          <p style={styles.syncDetail}>
            {isSyncing
              ? "Synchronisation en cours…"
              : syncStatus
              ? `${syncStatus.records_count?.toLocaleString() || 0} entrées à jour`
              : "Aucune sync"}
          </p>
        </div>
      </div>
    </aside>
  );
}

const styles = {
  sidebar: {
    width: "250px",
    backgroundColor: "var(--bg-sidebar)",
    borderRight: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    padding: "1.25rem 0.9rem",
    userSelect: "none",
    zIndex: 30,
  },
  brandContainer: {
    display: "flex",
    alignItems: "center",
    gap: "0.85rem",
    padding: "0.4rem 0.6rem 1.4rem",
    borderBottom: "1px solid var(--border)",
  },
  logoMark: {
    width: "36px",
    height: "36px",
    borderRadius: "10px",
    background: "linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 4px 16px rgba(79, 70, 229, 0.35)",
  },
  logoText: {
    fontWeight: "800",
    fontSize: "0.88rem",
    color: "#fff",
    letterSpacing: "-0.03em",
  },
  brandTitle: {
    fontSize: "0.95rem",
    fontWeight: "700",
    color: "var(--text-main)",
    letterSpacing: "-0.02em",
    lineHeight: "1.2",
  },
  brandSubtitle: {
    fontSize: "0.72rem",
    color: "var(--text-sub)",
    fontWeight: "500",
    marginTop: "1px",
  },
  navSection: {
    display: "flex",
    flexDirection: "column",
    marginTop: "1.25rem",
    flex: 1,
  },
  sectionLabel: {
    fontSize: "0.7rem",
    fontWeight: "600",
    color: "var(--text-sub)",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    padding: "0 0.75rem 0.6rem",
  },
  nav: {
    display: "flex",
    flexDirection: "column",
    gap: "0.2rem",
  },
  navButton: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    padding: "0.58rem 0.75rem",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-muted)",
    fontWeight: "500",
    fontSize: "0.86rem",
    transition: "all 0.15s cubic-bezier(0.16, 1, 0.3, 1)",
    textAlign: "left",
    position: "relative",
  },
  navButtonActive: {
    backgroundColor: "rgba(99, 102, 241, 0.1)",
    color: "#fff",
    fontWeight: "600",
  },
  navIconWrap: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  navLabel: {
    flex: 1,
  },
  activePillIndicator: {
    position: "absolute",
    left: "0",
    top: "20%",
    bottom: "20%",
    width: "3px",
    borderRadius: "0 4px 4px 0",
    backgroundColor: "var(--accent)",
    boxShadow: "0 0 8px rgba(99, 102, 241, 0.8)",
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
    gap: "0.65rem",
    padding: "0.65rem 0.85rem",
    borderRadius: "var(--radius-sm)",
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    color: "var(--text-main)",
    fontWeight: "600",
    fontSize: "0.85rem",
    transition: "all 0.15s ease",
    boxShadow: "var(--shadow-sm)",
  },
  chatToggleActive: {
    background: "linear-gradient(135deg, rgba(99, 102, 241, 0.2) 0%, rgba(56, 189, 248, 0.1) 100%)",
    borderColor: "var(--accent-border)",
    color: "#fff",
    boxShadow: "0 0 15px rgba(99, 102, 241, 0.2)",
  },
  chatIconWrap: {
    width: "24px",
    height: "24px",
    borderRadius: "6px",
    backgroundColor: "rgba(99, 102, 241, 0.15)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  syncCard: {
    padding: "0.75rem 0.85rem",
    backgroundColor: "rgba(0, 0, 0, 0.25)",
    borderRadius: "var(--radius-sm)",
    border: "1px solid var(--border)",
  },
  syncHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  syncIndicator: {
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
  },
  syncDot: {
    width: "7px",
    height: "7px",
    borderRadius: "50%",
  },
  syncTitle: {
    fontSize: "0.75rem",
    fontWeight: "600",
    color: "var(--text-muted)",
    letterSpacing: "0.02em",
  },
  syncBtn: {
    padding: "0.25rem",
    borderRadius: "4px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "background-color 0.15s",
  },
  syncDetail: {
    fontSize: "0.73rem",
    color: "var(--text-sub)",
    marginTop: "0.35rem",
  },
};
