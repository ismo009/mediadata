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
            {data.total.toLocaleString()} enregistrements trouvés
          </p>
        </div>

        <div style={styles.controls}>
          <div style={styles.searchWrap}>
            <Search size={15} color="var(--text-muted)" style={styles.searchIcon} />
            <input
              type="text"
              placeholder={`Rechercher ${entityTitle.toLowerCase()}...`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={styles.searchInput}
            />
          </div>

          <div style={styles.filterWrap}>
            <Filter size={14} color="var(--text-muted)" />
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

      {/* Table Content */}
      <div style={styles.tableCard}>
        {loading ? (
          <div style={styles.loadingContainer}>
            <Loader2 size={28} className="spin" color="var(--accent)" />
          </div>
        ) : data.records.length === 0 ? (
          <div style={styles.emptyContainer}>
            Aucun enregistrement correspondant.
          </div>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr style={styles.tableHeadRow}>
                <th style={{ ...styles.th, width: "70px" }}>ID</th>
                <th style={styles.th}>Nom / Code</th>
                <th style={styles.th}>Projet</th>
                <th style={styles.th}>Statut</th>
                <th style={styles.th}>Détails / Assigné</th>
                <th style={{ ...styles.th, width: "60px", textAlign: "right" }}>Lien</th>
              </tr>
            </thead>
            <tbody>
              {data.records.map((r) => {
                const name = r.name || r.code || r.cached_display_name || `#${r.id}`;
                const projName = r.project?.name || (typeof r.project === "string" ? r.project : "—");
                const st = r.sg_status_list || r.sg_status;
                const assignees = r.task_assignees ? r.task_assignees.map((u) => u.name).join(", ") : null;
                const noteSnippet = r.content || r.subject;

                return (
                  <tr key={r.id} style={styles.tr}>
                    <td style={{ ...styles.td, color: "var(--text-sub)", fontSize: "0.8rem" }}>
                      #{r.id}
                    </td>
                    <td style={{ ...styles.td, fontWeight: "600", color: "var(--text-main)" }}>
                      {name}
                    </td>
                    <td style={{ ...styles.td, color: "var(--text-muted)" }}>
                      {projName}
                    </td>
                    <td style={styles.td}>
                      {st ? (
                        <span className={`badge ${st === "fin" || st === "apr" ? "badge-fin" : "badge-wtg"}`}>
                          {st}
                        </span>
                      ) : (
                        <span style={{ color: "var(--text-sub)", fontSize: "0.75rem" }}>—</span>
                      )}
                    </td>
                    <td style={{ ...styles.td, color: "var(--text-muted)", fontSize: "0.82rem" }}>
                      {assignees && <span>Assigné : {assignees}</span>}
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
                          title="Ouvrir dans ShotGrid"
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
            Page {data.page} sur {data.pages || 1}
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
              <ChevronLeft size={16} />
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
              <ChevronRight size={16} />
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
    gap: "1.25rem",
  },
  header: {
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: "1rem",
  },
  title: {
    fontSize: "1.35rem",
    fontWeight: "700",
    color: "var(--text-main)",
  },
  subtitle: {
    fontSize: "0.85rem",
    color: "var(--text-muted)",
    marginTop: "0.2rem",
  },
  controls: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    flexWrap: "wrap",
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
    width: "240px",
  },
  filterWrap: {
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
    backgroundColor: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    padding: "0.45rem 0.75rem",
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
  },
  loadingContainer: {
    padding: "4rem",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  emptyContainer: {
    padding: "3rem",
    textAlign: "center",
    color: "var(--text-muted)",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    textAlign: "left",
  },
  tableHeadRow: {
    backgroundColor: "rgba(0, 0, 0, 0.2)",
    borderBottom: "1px solid var(--border)",
  },
  th: {
    padding: "0.75rem 1rem",
    fontSize: "0.78rem",
    fontWeight: "600",
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  },
  tr: {
    borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
    transition: "background-color 0.1s",
  },
  td: {
    padding: "0.85rem 1rem",
    fontSize: "0.88rem",
  },
  snippetText: {
    display: "-webkit-box",
    WebkitLineClamp: 1,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
  },
  linkIcon: {
    color: "var(--text-muted)",
    padding: "4px",
    display: "inline-flex",
  },
  pagination: {
    padding: "0.75rem 1.25rem",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    borderTop: "1px solid var(--border)",
    backgroundColor: "rgba(0, 0, 0, 0.15)",
  },
  pageInfo: {
    fontSize: "0.8rem",
    color: "var(--text-muted)",
  },
  pageButtons: {
    display: "flex",
    gap: "0.5rem",
  },
  pageBtn: {
    display: "flex",
    alignItems: "center",
    gap: "0.3rem",
    padding: "0.4rem 0.75rem",
    borderRadius: "var(--radius-sm)",
    backgroundColor: "var(--bg-input)",
    border: "1px solid var(--border)",
    color: "var(--text-main)",
    fontSize: "0.8rem",
    fontWeight: "500",
  },
  pageBtnDisabled: {
    opacity: 0.4,
    cursor: "not-allowed",
  },
};
