import React, { useState, useRef, useEffect } from "react";
import Markdown from "react-markdown";
import {
  Send,
  Square,
  Sparkles,
  Bot,
  User,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Trash2,
  Cpu,
  CornerDownLeft,
} from "lucide-react";
import { streamChatQuery, fetchModels } from "../api";

const QUICK_PROMPTS = [
  "Quels sont les projets actuellement actifs ?",
  "Y a-t-il des tâches bloquées ou en attente ?",
  "Résume les dernières notes de production",
  "Qui travaille sur les plans d'animation ?",
];

export default function ChatAssistant({ isOpen, onClose }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Bonjour ! Je suis l'assistant Studio Ops. Posez-moi une question sur vos projets ShotGrid ou vos documents Google Drive.",
      sources: null,
    },
  ]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [abortController, setAbortController] = useState(null);

  const messagesEndRef = useRef(null);

  useEffect(() => {
    fetchModels().then((data) => {
      setModels(data.models || []);
      if (data.default) setSelectedModel(data.default);
      else if (data.models?.length > 0) setSelectedModel(data.models[0]);
    });
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  const handleSend = (textToSend = null) => {
    const question = (textToSend || input).trim();
    if (!question || isStreaming) return;

    setInput("");
    const newHistory = [...messages, { role: "user", content: question }];
    setMessages(newHistory);

    const assistantIndex = newHistory.length;
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", sources: null, isLive: true },
    ]);

    setIsStreaming(true);

    const cleanHistory = newHistory
      .filter((m) => m.content && m.content.trim())
      .map((m) => ({
        role: m.role,
        content: m.content,
      }))
      .slice(-10);

    const controller = streamChatQuery({
      question,
      history: cleanHistory,
      model: selectedModel || undefined,
      onSources: (sources) => {
        setMessages((prev) => {
          const next = [...prev];
          if (next[assistantIndex]) {
            next[assistantIndex].sources = sources;
          }
          return next;
        });
      },
      onToken: (token) => {
        setMessages((prev) => {
          const next = [...prev];
          if (next[assistantIndex]) {
            next[assistantIndex].content += token;
          }
          return next;
        });
      },
      onError: (err) => {
        setMessages((prev) => {
          const next = [...prev];
          if (next[assistantIndex]) {
            next[assistantIndex].content += `\n\n⚠️ **Erreur :** ${err.message}`;
            next[assistantIndex].isLive = false;
          }
          return next;
        });
        setIsStreaming(false);
      },
      onDone: () => {
        setMessages((prev) => {
          const next = [...prev];
          if (next[assistantIndex]) {
            next[assistantIndex].isLive = false;
          }
          return next;
        });
        setIsStreaming(false);
      },
    });

    setAbortController(controller);
  };

  const handleStop = () => {
    if (abortController) {
      abortController.abort();
      setIsStreaming(false);
    }
  };

  const handleClear = () => {
    setMessages([
      {
        role: "assistant",
        content: "Historique réinitialisé. Comment puis-je vous aider ?",
        sources: null,
      },
    ]);
  };

  if (!isOpen) return null;

  return (
    <aside style={styles.drawer}>
      {/* Drawer Header */}
      <div style={styles.header}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
          <div style={styles.botIconBadge}>
            <Sparkles size={16} color="var(--accent)" />
          </div>
          <div>
            <h3 style={styles.headerTitle}>Assistant IA</h3>
            <div style={styles.modelSelectorWrap}>
              <Cpu size={12} color="var(--text-sub)" />
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                style={styles.modelSelect}
              >
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <button onClick={handleClear} style={styles.iconBtn} title="Effacer la conversation">
          <Trash2 size={15} />
        </button>
      </div>

      {/* Messages Scroll Area */}
      <div style={styles.messagesList}>
        {messages.map((msg, idx) => {
          const isUser = msg.role === "user";
          return (
            <div
              key={idx}
              style={{
                ...styles.messageWrap,
                justifyContent: isUser ? "flex-end" : "flex-start",
              }}
            >
              {!isUser && (
                <div style={styles.avatarBot}>
                  <Bot size={14} color="#fff" />
                </div>
              )}

              <div
                style={{
                  ...styles.bubble,
                  ...(isUser ? styles.bubbleUser : styles.bubbleBot),
                }}
              >
                {msg.sources && <SourcesDrawer sources={msg.sources} />}

                <div className="prose">
                  <Markdown>{msg.content || (msg.isLive ? "…" : "")}</Markdown>
                </div>
              </div>

              {isUser && (
                <div style={styles.avatarUser}>
                  <User size={14} color="#fff" />
                </div>
              )}
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions Pills */}
      {messages.length <= 2 && (
        <div style={styles.quickPromptsWrap}>
          <span style={styles.quickLabel}>Suggestions :</span>
          <div style={styles.quickPills}>
            {QUICK_PROMPTS.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSend(q)}
                style={styles.quickPill}
              >
                <span>{q}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Composer */}
      <div style={styles.inputArea}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          style={styles.form}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Posez votre question (ex. Tâches de John)..."
            rows={1}
            style={styles.textarea}
          />

          {isStreaming ? (
            <button
              type="button"
              onClick={handleStop}
              style={styles.stopButton}
              title="Interrompre la réponse"
            >
              <Square size={14} />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              style={{
                ...styles.sendButton,
                ...(!input.trim() ? styles.sendDisabled : {}),
              }}
              title="Envoyer (Entrée)"
            >
              <CornerDownLeft size={14} />
            </button>
          )}
        </form>
      </div>
    </aside>
  );
}

function decodeHtml(html) {
  if (!html) return "";
  return html
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function SourcesDrawer({ sources }) {
  const [open, setOpen] = useState(false);
  const shotgrid = sources.shotgrid || [];
  const drive = sources.google_drive || [];
  const sgCount = shotgrid.length;
  const driveCount = drive.length;

  if (sgCount === 0 && driveCount === 0) return null;

  // Breakdown of entities
  const typeCounts = shotgrid.reduce((acc, s) => {
    const t = s.type || "Entité";
    acc[t] = (acc[t] || 0) + 1;
    return acc;
  }, {});
  const breakdownStr = Object.entries(typeCounts)
    .map(([t, c]) => `${c} ${t}${c > 1 ? "s" : ""}`)
    .join(", ");

  return (
    <div style={styles.sourcesBox}>
      <button onClick={() => setOpen(!open)} style={styles.sourcesHeader}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>
          {sgCount} source{sgCount > 1 ? "s" : ""} ShotGrid ({breakdownStr || "données"})
          {driveCount > 0 ? `, ${driveCount} Drive` : ""}
        </span>
      </button>

      {open && (
        <div style={styles.sourcesList}>
          {shotgrid.map((s, idx) => (
            <div key={idx} style={styles.sourceItem}>
              <span className="badge badge-default" style={{ fontSize: "0.65rem", padding: "0.15rem 0.45rem" }}>
                {s.type}
              </span>
              <span style={{ fontSize: "0.78rem", color: "var(--text-main)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {decodeHtml(s.name || `#${s.id}`)}
              </span>
              {s.source_url && (
                <a
                  href={s.source_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ marginLeft: "auto", color: "var(--accent)" }}
                  title="Voir dans ShotGrid"
                >
                  <ExternalLink size={12} />
                </a>
              )}
            </div>
          ))}
          {drive.map((d, idx) => (
            <div key={idx} style={styles.sourceItem}>
              <span className="badge badge-default" style={{ fontSize: "0.65rem", padding: "0.15rem 0.45rem" }}>
                Drive
              </span>
              <span style={{ fontSize: "0.78rem", color: "var(--text-main)" }}>
                {d.name}
              </span>
              {d.webViewLink && (
                <a
                  href={d.webViewLink}
                  target="_blank"
                  rel="noreferrer"
                  style={{ marginLeft: "auto", color: "var(--accent)" }}
                >
                  <ExternalLink size={12} />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const styles = {
  drawer: {
    width: "430px",
    backgroundColor: "var(--bg-sidebar)",
    borderLeft: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    height: "100%",
    boxShadow: "var(--shadow-lg)",
    zIndex: 25,
  },
  header: {
    padding: "1.1rem 1.4rem",
    borderBottom: "1px solid var(--border)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "rgba(14, 17, 23, 0.9)",
    backdropFilter: "blur(12px)",
  },
  botIconBadge: {
    width: "34px",
    height: "34px",
    borderRadius: "10px",
    background: "linear-gradient(135deg, rgba(99, 102, 241, 0.2) 0%, rgba(56, 189, 248, 0.1) 100%)",
    border: "1px solid var(--accent-border)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  headerTitle: {
    fontSize: "0.95rem",
    fontWeight: "700",
    color: "var(--text-main)",
    letterSpacing: "-0.01em",
  },
  modelSelectorWrap: {
    display: "flex",
    alignItems: "center",
    gap: "0.35rem",
    marginTop: "2px",
  },
  modelSelect: {
    background: "transparent",
    border: "none",
    fontSize: "0.75rem",
    color: "var(--text-muted)",
    outline: "none",
    cursor: "pointer",
    fontWeight: "500",
  },
  iconBtn: {
    color: "var(--text-sub)",
    padding: "0.45rem",
    borderRadius: "var(--radius-sm)",
    transition: "color 0.15s",
  },
  messagesList: {
    flex: 1,
    overflowY: "auto",
    padding: "1.4rem",
    display: "flex",
    flexDirection: "column",
    gap: "1.25rem",
  },
  messageWrap: {
    display: "flex",
    gap: "0.65rem",
    maxWidth: "100%",
  },
  avatarBot: {
    width: "28px",
    height: "28px",
    borderRadius: "8px",
    background: "linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    marginTop: "2px",
    boxShadow: "0 2px 8px rgba(79, 70, 229, 0.3)",
  },
  avatarUser: {
    width: "28px",
    height: "28px",
    borderRadius: "8px",
    backgroundColor: "#2d3748",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    marginTop: "2px",
  },
  bubble: {
    padding: "0.9rem 1.15rem",
    borderRadius: "var(--radius)",
    maxWidth: "88%",
    wordBreak: "break-word",
  },
  bubbleUser: {
    background: "linear-gradient(135deg, rgba(99, 102, 241, 0.18) 0%, rgba(79, 70, 229, 0.1) 100%)",
    border: "1px solid var(--accent-border)",
    color: "var(--text-main)",
  },
  bubbleBot: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    color: "var(--text-main)",
    boxShadow: "var(--shadow-card)",
  },
  sourcesBox: {
    marginBottom: "0.75rem",
    paddingBottom: "0.6rem",
    borderBottom: "1px solid var(--border)",
  },
  sourcesHeader: {
    display: "flex",
    alignItems: "center",
    gap: "0.35rem",
    fontSize: "0.74rem",
    color: "var(--accent)",
    fontWeight: "600",
  },
  sourcesList: {
    marginTop: "0.5rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.35rem",
    maxHeight: "220px",
    overflowY: "auto",
    paddingRight: "4px",
  },
  sourceItem: {
    display: "flex",
    alignItems: "center",
    gap: "0.45rem",
    backgroundColor: "rgba(0, 0, 0, 0.3)",
    padding: "0.3rem 0.6rem",
    borderRadius: "6px",
    border: "1px solid rgba(255, 255, 255, 0.04)",
  },
  quickPromptsWrap: {
    padding: "0.85rem 1.4rem",
    borderTop: "1px solid var(--border)",
    backgroundColor: "rgba(0, 0, 0, 0.15)",
  },
  quickLabel: {
    fontSize: "0.72rem",
    color: "var(--text-sub)",
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    display: "block",
    marginBottom: "0.5rem",
  },
  quickPills: {
    display: "flex",
    flexDirection: "column",
    gap: "0.4rem",
  },
  quickPill: {
    textAlign: "left",
    fontSize: "0.8rem",
    color: "var(--text-muted)",
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    padding: "0.45rem 0.75rem",
    borderRadius: "var(--radius-sm)",
    transition: "all 0.15s ease",
  },
  inputArea: {
    padding: "1rem 1.4rem 1.4rem",
    borderTop: "1px solid var(--border)",
    backgroundColor: "var(--bg-sidebar)",
  },
  form: {
    display: "flex",
    alignItems: "center",
    gap: "0.6rem",
    backgroundColor: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: "0.45rem 0.7rem",
    boxShadow: "0 2px 8px rgba(0, 0, 0, 0.25) inset",
  },
  textarea: {
    flex: 1,
    border: "none",
    background: "transparent",
    color: "var(--text-main)",
    outline: "none",
    fontSize: "0.86rem",
    resize: "none",
    maxHeight: "90px",
    padding: "0.2rem",
  },
  sendButton: {
    width: "32px",
    height: "32px",
    borderRadius: "8px",
    background: "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "all 0.15s ease",
    boxShadow: "0 2px 8px rgba(99, 102, 241, 0.35)",
  },
  sendDisabled: {
    opacity: 0.25,
    cursor: "not-allowed",
    boxShadow: "none",
  },
  stopButton: {
    width: "32px",
    height: "32px",
    borderRadius: "8px",
    backgroundColor: "var(--danger)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
};
