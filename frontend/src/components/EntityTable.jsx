import React, { useState, useEffect } from "react";
import { Search, ChevronLeft, ChevronRight, ExternalLink, Loader2, Filter } from "lucide-react";
import { fetchEntityData } from "../api";

export default function EntityTable({ entity, entityTitle }) {
  const [data, setData] = useState({ records: [], total: 0, page: 1, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [status, setStatus] = useState("");

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Fetch when page, search, or status changes
  useEffect(() => {
    setLoading(true);
    fetchEntityData({
      entity,
      page,
      limit: 25,
      search: debouncedSearch,
      status,
    })
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, [entity, page, debouncedSearch, status]);

  return (
    <div style={styles.container}>
      {/* Header & Controls */}
      <div style={styles.header}>
        <div>
          <h2 style={styles.title}>{entityTitle}</h2>
          <p style={styles.subtitle}>
            {data.total.toLocaleString()} enregistrements indexés dans le cache
          </p>
        </div>

        <div style={styles.controls}>
          <div style={styles.searchWrap}>
            <Search size={15} color="var(--text-sub)" style={styles.searchIcon} />
            <input
              type="text"
              placeholder={`Filtrer les ${entityTitle.toLowerCase()}...`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={styles.searchInput}
            />
          </div>

          <div style={styles.filterWrap}>
            <Filter size={14} color="var(--text-sub)" />
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
              style={styles.select}
            >
              <option value="">Tous les statuts</option>
              <option value="fin">Terminé (fin)</option>
              <option value="ip">En cours (ip)</option>
              <option value="wtg">En attente (wtg)</option>
              <option value="rev">À revoir (rev)</option>
              <option value="opn">Ouvert (opn)</option>
              <option value="act">Actif (act)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table Card */}
      <div style={styles.tableCard}>
        {loading ? (
          <div style={styles.loadingContainer}>
            <Loader2 size={30} className="spin" color="var(--accent)" />
          </div>
        ) : data.records.length === 0 ? (
          <div style={styles.emptyContainer}>
            Aucun enregistrement ne correspond aux critères de recherche.
          </div>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr style={styles.tableHeadRow}>
                <th style={{ ...styles.th, width: "80px" }}>ID</th>
                <th style={styles.th}>Nom / Désignation</th>
                <th style={styles.th}>Projet Lié</th>
                <th style={styles.th}>Statut</th>
                <th style={styles.th}>Assigné / Contenu</th>
                <th style={{ ...styles.th, width: "70px", textAlign: "right" }}>Lien</th>
              </tr>
            </thead>
            <tbody>
              {data.records.map((r) => {
                const name = r.name || r.code || r.cached_display_name || `#${r.id}`;
                const projName = r.project?.name || (typeof r.project === "string" ? r.project : "—");
                const st = r.sg_status_list || r.sg_status;
                const isFin = st === "fin" || st === "apr";
                const assignees = r.task_assignees ? r.task_assignees.map((u) => u.name).join(", ") : null;
                const noteSnippet = r.content || r.subject;

                return (
                  <tr key={r.id} style={styles.tr}>
                    <td style={styles.idCell}>
                      #{r.id}
                    </td>
                    <td style={styles.nameCell}>
                      {name}
                    </td>
                    <td style={styles.projectCell}>
                      {projName}
                    </td>
                    <td style={styles.td}>
                      {st ? (
                        <span className={`badge ${isFin ? "badge-fin" : "badge-wtg"}`}>
                          {st}
                        </span>
                      ) : (
                        <span style={{ color: "var(--text-sub)", fontSize: "0.75rem" }}>—</span>
                      )}
                    </td>
                    <td style={styles.detailCell}>
                      {assignees && <span style={styles.assigneeBadge}>{assignees}</span>}
                      {noteSnippet && <span style={styles.snippetText}>{noteSnippet}</span>}
                      {!assignees && !noteSnippet && <span>—</span>}
                    </td>
                    <td style={{ ...styles.td, textAlign: "right" }}>
                      {r.source_url && (
                        <a
                          href={r.source_url}
                          target="_blank"
                          rel="noreferrer"
                          style={styles.linkIcon}
                          title="Consulter sur ShotGrid"
                        >
                          <ExternalLink size={14} />
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {/* Pagination Footer */}
        <div style={styles.pagination}>
          <span style={styles.pageInfo}>
            Page <strong style={{ color: "var(--text-main)" }}>{data.page}</strong> sur{" "}
            <strong style={{ color: "var(--text-main)" }}>{data.pages || 1}</strong>
          </span>
          <div style={styles.pageButtons}>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={data.page <= 1 || loading}
              style={{
                ...styles.pageBtn,
                ...(data.page <= 1 ? styles.pageBtnDisabled : {}),
              }}
            >
              <ChevronLeft size={15} />
              Précédent
            </button>
            <button
              onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
              disabled={data.page >= data.pages || loading}
              style={{
                ...styles.pageBtn,
                ...(data.page >= data.pages ? styles.pageBtnDisabled : {}),
              }}
            >
              Suivant
              <ChevronRight size={15} />
            </button>
          </div>
        </div>
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
  header: {
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: "1.25rem",
  },
  title: {
    fontSize: "1.45rem",
    fontWeight: "700",
    color: "var(--text-main)",
    letterSpacing: "-0.02em",
  },
  subtitle: {
    fontSize: "0.85rem",
    color: "var(--text-muted)",
    marginTop: "0.2rem",
  },
  controls: {
    display: "flex",
    alignItems: "center",
    gap: "0.85rem",
    flexWrap: "wrap",
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
  },
  filterWrap: {
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
    backgroundColor: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    padding: "0.5rem 0.85rem",
  },
  select: {
    background: "transparent",
    border: "none",
    color: "var(--text-main)",
    fontSize: "0.82rem",
    outline: "none",
    cursor: "pointer",
  },
  tableCard: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    overflow: "hidden",
    boxShadow: "var(--shadow-card)",
  },
  loadingContainer: {
    padding: "5rem",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  emptyContainer: {
    padding: "4rem 2rem",
    textAlign: "center",
    color: "var(--text-muted)",
    fontSize: "0.9rem",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    textAlign: "left",
  },
  tableHeadRow: {
    backgroundColor: "rgba(0, 0, 0, 0.3)",
    borderBottom: "1px solid var(--border)",
  },
  th: {
    padding: "0.85rem 1.25rem",
    fontSize: "0.72rem",
    fontWeight: "700",
    color: "var(--text-sub)",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  },
  tr: {
    borderBottom: "1px solid rgba(255, 255, 255, 0.03)",
    transition: "background-color 0.12s ease",
  },
  td: {
    padding: "0.9rem 1.25rem",
    fontSize: "0.88rem",
    verticalAlign: "middle",
  },
  idCell: {
    padding: "0.9rem 1.25rem",
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: "0.78rem",
    color: "var(--text-sub)",
  },
  nameCell: {
    padding: "0.9rem 1.25rem",
    fontWeight: "600",
    color: "var(--text-main)",
  },
  projectCell: {
    padding: "0.9rem 1.25rem",
    color: "var(--text-muted)",
    fontSize: "0.85rem",
  },
  detailCell: {
    padding: "0.9rem 1.25rem",
    fontSize: "0.82rem",
    color: "var(--text-muted)",
    maxWidth: "340px",
  },
  assigneeBadge: {
    color: "var(--text-main)",
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    padding: "0.2rem 0.5rem",
    borderRadius: "4px",
    border: "1px solid var(--border)",
  },
  snippetText: {
    display: "-webkit-box",
    WebkitLineClamp: 1,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
  },
  linkIcon: {
    color: "var(--text-sub)",
    padding: "4px",
    display: "inline-flex",
    borderRadius: "4px",
    transition: "color 0.15s",
  },
  pagination: {
    padding: "0.85rem 1.5rem",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    borderTop: "1px solid var(--border)",
    backgroundColor: "rgba(0, 0, 0, 0.2)",
  },
  pageInfo: {
    fontSize: "0.8rem",
    color: "var(--text-muted)",
  },
  pageButtons: {
    display: "flex",
    gap: "0.6rem",
  },
  pageBtn: {
    display: "flex",
    alignItems: "center",
    gap: "0.35rem",
    padding: "0.45rem 0.85rem",
    borderRadius: "var(--radius-sm)",
    backgroundColor: "var(--bg-input)",
    border: "1px solid var(--border)",
    color: "var(--text-main)",
    fontSize: "0.82rem",
    fontWeight: "500",
    transition: "all 0.15s ease",
  },
  pageBtnDisabled: {
    opacity: 0.35,
    cursor: "not-allowed",
  },
};
