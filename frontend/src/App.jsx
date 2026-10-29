import React, { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import DashboardOverview from "./components/DashboardOverview";
import ProjectDetail from "./components/ProjectDetail";
import EntityTable from "./components/EntityTable";
import ChatAssistant from "./components/ChatAssistant";
import { fetchDashboard, triggerSync, fetchSyncStatus } from "./api";

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
      // Poll sync status
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
          <div>
            <h2 style={{ fontSize: "1.1rem", fontWeight: "700" }}>
              {selectedProjectId
                ? "Détail du projet"
                : activeTab === "overview"
                ? "Vue d'ensemble de la production"
                : ENTITY_TITLES[currentEntity] || "Gestion"}
            </h2>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            {syncStatus && (
              <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                Dernière synchro :{" "}
                <strong style={{ color: "var(--text-main)" }}>
                  {new Date(syncStatus.finished_at || syncStatus.started_at).toLocaleDateString()}{" "}
                  {new Date(syncStatus.finished_at || syncStatus.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </strong>
              </span>
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
