import React, { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import DashboardOverview from "./components/DashboardOverview";
import ProjectDetail from "./components/ProjectDetail";
import EntityTable from "./components/EntityTable";
import ChatAssistant from "./components/ChatAssistant";
import { fetchDashboard, triggerSync, fetchSyncStatus } from "./api";
import { Sparkles, Clock } from "lucide-react";

const ENTITY_TITLES = {
  projects: "Projets",
  shots: "Shots (Plans)",
  tasks: "Tâches de production",
  assets: "Assets (Ressources)",
  versions: "Versions de review",
  notes: "Notes de production",
};

export default function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const [currentEntity, setCurrentEntity] = useState(null);
  const [selectedProjectId, setSelectedProjectId] = useState(null);

  const [dashboardData, setDashboardData] = useState(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState(null);

  const [chatOpen, setChatOpen] = useState(true);

  // Load Dashboard Data
  const loadDashboard = () => {
    fetchDashboard()
      .then((data) => {
        setDashboardData(data);
        if (data.last_sync) setSyncStatus(data.last_sync);
      })
      .catch((err) => console.error("Error loading dashboard:", err));
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  // Handle Tab Selection
  const handleSelectTab = (tabId, entity) => {
    setActiveTab(tabId);
    setSelectedProjectId(null);
    setCurrentEntity(entity || null);
  };

  // Handle Project Selection from Overview
  const handleSelectProject = (projectId) => {
    setSelectedProjectId(projectId);
  };

  // Trigger ShotGrid Sync
  const handleTriggerSync = async () => {
    if (isSyncing) return;
    setIsSyncing(true);
    try {
      await triggerSync();
      const interval = setInterval(async () => {
        try {
          const statusRes = await fetchSyncStatus();
          const sync = statusRes.last_sync;
          setSyncStatus(sync);
          if (sync && (sync.status === "completed" || sync.status === "failed")) {
            clearInterval(interval);
            setIsSyncing(false);
            loadDashboard();
          }
        } catch (e) {
          clearInterval(interval);
          setIsSyncing(false);
        }
      }, 2500);
    } catch (err) {
      alert(`Erreur de synchronisation : ${err.message}`);
      setIsSyncing(false);
    }
  };

  return (
    <div className="app-container">
      {/* Left Navigation Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={handleSelectTab}
        syncStatus={syncStatus}
        onTriggerSync={handleTriggerSync}
        isSyncing={isSyncing}
        chatOpen={chatOpen}
        onToggleChat={() => setChatOpen(!chatOpen)}
      />

      {/* Main Workspace */}
      <main className="main-content">
        <header className="content-header">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <h2 style={{ fontSize: "1.15rem", fontWeight: "700", letterSpacing: "-0.02em" }}>
              {selectedProjectId
                ? "Espace Projet"
                : activeTab === "overview"
                ? "Vue d'ensemble de la production"
                : ENTITY_TITLES[currentEntity] || "Gestion"}
            </h2>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            {syncStatus && (
              <div style={styles.syncMetaPill}>
                <Clock size={13} color="var(--text-sub)" />
                <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                  Sync ShotGrid :{" "}
                  <strong style={{ color: "var(--text-main)", fontWeight: "600" }}>
                    {new Date(syncStatus.finished_at || syncStatus.started_at).toLocaleDateString([], { month: "short", day: "numeric" })}{" "}
                    à {new Date(syncStatus.finished_at || syncStatus.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </strong>
                </span>
              </div>
            )}

            {!chatOpen && (
              <button
                onClick={() => setChatOpen(true)}
                style={styles.openAssistantBtn}
                title="Ouvrir l'Assistant IA"
              >
                <Sparkles size={14} color="var(--accent)" />
                <span>Assistant</span>
              </button>
            )}
          </div>
        </header>

        <div className="content-body">
          {selectedProjectId ? (
            <ProjectDetail
              projectId={selectedProjectId}
              onBack={() => setSelectedProjectId(null)}
            />
          ) : activeTab === "overview" ? (
            <DashboardOverview
              dashboardData={dashboardData}
              onSelectProject={handleSelectProject}
            />
          ) : (
            <EntityTable
              key={currentEntity}
              entity={currentEntity}
              entityTitle={ENTITY_TITLES[currentEntity] || currentEntity}
            />
          )}
        </div>
      </main>

      {/* Right AI Assistant Drawer */}
      <ChatAssistant
        isOpen={chatOpen}
        onClose={() => setChatOpen(false)}
      />
    </div>
  );
}

const styles = {
  syncMetaPill: {
    display: "flex",
    alignItems: "center",
    gap: "0.45rem",
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    padding: "0.35rem 0.75rem",
    borderRadius: "var(--radius-full)",
    border: "1px solid var(--border)",
  },
  openAssistantBtn: {
    display: "flex",
    alignItems: "center",
    gap: "0.45rem",
    padding: "0.45rem 0.85rem",
    borderRadius: "var(--radius-sm)",
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    color: "var(--text-main)",
    fontSize: "0.82rem",
    fontWeight: "600",
    transition: "all 0.15s ease",
  },
};
