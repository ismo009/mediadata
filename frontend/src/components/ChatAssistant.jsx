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
} from "lucide-react";
import { streamChatQuery, fetchModels } from "../api";

const QUICK_PROMPTS = [
  "Quels sont les projets actuellement actifs ?",
  "Y a-t-il des tâches en attente de validation ?",
  "Résume les dernières notes du projet",
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

    // Placeholder for incoming streaming assistant response
    const assistantIndex = newHistory.length;
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", sources: null, isLive: true },
    ]);

    setIsStreaming(true);

    const controller = streamChatQuery({
      question,
      history: newHistory.slice(-10),
      model: selectedModel,
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
      {/* Header */}
      <div style={styles.header}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div style={styles.botIconBadge}>
            <Sparkles size={16} color="var(--accent)" />
          </div>
          <div>
            <h3 style={styles.headerTitle}>Assistant Studio Ops</h3>
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

        <div style={{ display: "flex", gap: "0.35rem" }}>
          <button onClick={handleClear} style={styles.iconBtn} title="Effacer la discussion">
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {/* Messages */}
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
                  <Bot size={15} color="#fff" />
                </div>
              )}

              <div
                style={{
                  ...styles.bubble,
                  ...(isUser ? styles.bubbleUser : styles.bubbleBot),
                }}
              >
                {/* Sources pill if present */}
                {msg.sources && (
                  <SourcesDrawer sources={msg.sources} />
                )}

                <div className="prose">
                  <Markdown>{msg.content || (msg.isLive ? "…" : "")}</Markdown>
                </div>
              </div>

              {isUser && (
                <div style={styles.avatarUser}>
                  <User size={15} color="#fff" />
                </div>
              )}
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions if few messages */}
      {messages.length <= 2 && (
        <div style={styles.quickPromptsWrap}>
          <p style={styles.quickLabel}>Questions suggérées :</p>
          <div style={styles.quickPills}>
            {QUICK_PROMPTS.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSend(q)}
                style={styles.quickPill}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Form */}
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
            placeholder="Posez votre question sur la production..."
            rows={1}
            style={styles.textarea}
          />

          {isStreaming ? (
            <button
              type="button"
              onClick={handleStop}
              style={styles.stopButton}
              title="Arrêter la réponse"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              style={{
                ...styles.sendButton,
                ...(!input.trim() ? styles.sendDisabled : {}),
              }}
              title="Envoyer"
            >
              <Send size={16} />
            </button>
          )}
        </form>
      </div>
    </aside>
  );
}

function SourcesDrawer({ sources }) {
  const [open, setOpen] = useState(false);
  const sgCount = sources.shotgrid?.length || 0;
  const driveCount = sources.google_drive?.length || 0;

  if (sgCount === 0 && driveCount === 0) return null;

  return (
    <div style={styles.sourcesBox}>
      <button onClick={() => setOpen(!open)} style={styles.sourcesHeader}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>
          Sources inspectées : {sgCount} ShotGrid, {driveCount} Drive
        </span>
      </button>

      {open && (
        <div style={styles.sourcesList}>
          {sources.shotgrid?.map((s, idx) => (
            <div key={idx} style={styles.sourceItem}>
              <span className="badge badge-default" style={{ fontSize: "0.68rem" }}>
                {s.type}
              </span>
              <span style={{ fontSize: "0.8rem", color: "var(--text-main)" }}>
                {s.name || `#${s.id}`}
              </span>
              {s.source_url && (
                <a
                  href={s.source_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ marginLeft: "auto", color: "var(--accent)" }}
                >
                  <ExternalLink size={12} />
                </a>
              )}
            </div>
          ))}
          {sources.google_drive?.map((d, idx) => (
            <div key={idx} style={styles.sourceItem}>
              <span className="badge badge-default" style={{ fontSize: "0.68rem" }}>
                Drive
              </span>
              <span style={{ fontSize: "0.8rem", color: "var(--text-main)" }}>
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
    width: "420px",
    backgroundColor: "var(--bg-sidebar)",
    borderLeft: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    height: "100%",
  },
  header: {
    padding: "1rem 1.25rem",
    borderBottom: "1px solid var(--border)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "rgba(15, 23, 42, 0.6)",
  },
  botIconBadge: {
    width: "32px",
    height: "32px",
    borderRadius: "8px",
    backgroundColor: "var(--accent-soft)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  headerTitle: {
    fontSize: "0.95rem",
    fontWeight: "700",
    color: "var(--text-main)",
  },
  modelSelectorWrap: {
    display: "flex",
    alignItems: "center",
    gap: "0.35rem",
    marginTop: "0.15rem",
  },
  modelSelect: {
    background: "transparent",
    border: "none",
    fontSize: "0.75rem",
    color: "var(--text-muted)",
    outline: "none",
    cursor: "pointer",
  },
  iconBtn: {
    color: "var(--text-muted)",
    padding: "0.4rem",
    borderRadius: "var(--radius-sm)",
    transition: "color 0.15s",
  },
  messagesList: {
    flex: 1,
    overflowY: "auto",
    padding: "1.25rem",
    display: "flex",
    flexDirection: "column",
    gap: "1.25rem",
  },
  messageWrap: {
    display: "flex",
    gap: "0.6rem",
    maxWidth: "100%",
  },
  avatarBot: {
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    backgroundColor: "#0284c7",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    marginTop: "2px",
  },
  avatarUser: {
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    backgroundColor: "#475569",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    marginTop: "2px",
  },
  bubble: {
    padding: "0.85rem 1rem",
    borderRadius: "var(--radius)",
    maxWidth: "85%",
    wordBreak: "break-word",
  },
  bubbleUser: {
    backgroundColor: "var(--accent-soft)",
    border: "1px solid rgba(56, 189, 248, 0.25)",
    color: "var(--text-main)",
  },
  bubbleBot: {
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    color: "var(--text-main)",
  },
  sourcesBox: {
    marginBottom: "0.65rem",
    paddingBottom: "0.5rem",
    borderBottom: "1px solid var(--border)",
  },
  sourcesHeader: {
    display: "flex",
    alignItems: "center",
    gap: "0.3rem",
    fontSize: "0.75rem",
    color: "var(--accent)",
    fontWeight: "600",
  },
  sourcesList: {
    marginTop: "0.4rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.3rem",
  },
  sourceItem: {
    display: "flex",
    alignItems: "center",
    gap: "0.4rem",
    backgroundColor: "rgba(0, 0, 0, 0.25)",
    padding: "0.25rem 0.5rem",
    borderRadius: "4px",
  },
  quickPromptsWrap: {
    padding: "0.75rem 1.25rem",
    borderTop: "1px solid var(--border)",
    backgroundColor: "rgba(0, 0, 0, 0.15)",
  },
  quickLabel: {
    fontSize: "0.75rem",
    color: "var(--text-sub)",
    marginBottom: "0.4rem",
  },
  quickPills: {
    display: "flex",
    flexDirection: "column",
    gap: "0.35rem",
  },
  quickPill: {
    textAlign: "left",
    fontSize: "0.78rem",
    color: "var(--accent)",
    backgroundColor: "var(--bg-card)",
    border: "1px solid var(--border)",
    padding: "0.4rem 0.6rem",
    borderRadius: "var(--radius-sm)",
    transition: "all 0.15s ease",
  },
  inputArea: {
    padding: "1rem 1.25rem",
    borderTop: "1px solid var(--border)",
    backgroundColor: "var(--bg-card)",
  },
  form: {
    display: "flex",
    alignItems: "center",
    gap: "0.6rem",
    backgroundColor: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: "0.4rem 0.6rem",
  },
  textarea: {
    flex: 1,
    border: "none",
    background: "transparent",
    color: "var(--text-main)",
    outline: "none",
    fontSize: "0.88rem",
    resize: "none",
    maxHeight: "100px",
  },
  sendButton: {
    width: "32px",
    height: "32px",
    borderRadius: "var(--radius-sm)",
    backgroundColor: "var(--accent)",
    color: "#0b1120",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "all 0.15s ease",
  },
  sendDisabled: {
    opacity: 0.3,
    cursor: "not-allowed",
  },
  stopButton: {
    width: "32px",
    height: "32px",
    borderRadius: "var(--radius-sm)",
    backgroundColor: "var(--danger)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
};
