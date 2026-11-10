import React from "react";
import { useApp } from "../App";
import { navigate } from "../lib";
import TaskTable from "../components/TaskTable";

export default function MyTasksPage({ query }) {
  const { me } = useApp();
  return (
    <div className="page">
      <h1 className="display h1">Mes tâches</h1>
      <p className="lede">Les tâches qui vous sont assignées, toutes productions confondues.</p>
      <TaskTable
        base={{ person_id: me.id }}
        query={query}
        setQuery={(q) => navigate("/me", q)}
        showProject
        emptyText={Object.keys(query).length ? "Aucune de vos tâches ne correspond à ces filtres." : "Aucune tâche en cours ne vous est assignée dans ShotGrid."}
      />
    </div>
  );
}
