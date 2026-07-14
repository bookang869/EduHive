'use client';

import { useState, useRef, useEffect, useCallback } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const AGENTS = [
  { key: 'teacher_agent',        label: 'Teacher',  icon: '🧑‍🏫' },
  { key: 'feynman_agent',        label: 'Feynman',  icon: '🧠' },
  { key: 'quiz_agent',           label: 'Quiz',     icon: '📝' },
  { key: 'classification_agent', label: 'Classify', icon: '🗂️' },
];

const AGENT_LABEL = {
  classification_agent: 'Assessing…',
  teacher_agent:        'Teaching…',
  feynman_agent:        'Feynman…',
  quiz_agent:           'Quiz…',
};

function HexIcon({ size = 44 }) {
  const innerPct = '18%';
  return (
    <div style={{
      width: size, height: size, flexShrink: 0, position: 'relative',
      background: 'linear-gradient(135deg, #f6c454, #f59e0b)',
      clipPath: 'polygon(25% 6.7%, 75% 6.7%, 100% 50%, 75% 93.3%, 25% 93.3%, 0% 50%)',
      boxShadow: '0 8px 24px rgba(245,158,11,0.28)',
    }}>
      <div style={{
        position: 'absolute', inset: innerPct,
        background: 'var(--panel)',
        clipPath: 'polygon(25% 6.7%, 75% 6.7%, 100% 50%, 75% 93.3%, 25% 93.3%, 0% 50%)',
      }} />
    </div>
  );
}

export default function Page() {
  const [view,        setView]        = useState('upload');
  const [file,        setFile]        = useState(null);
  const [messages,    setMessages]    = useState([]);
  const [input,       setInput]       = useState('');
  const [connected,   setConnected]   = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const [dragOver,    setDragOver]    = useState(false);

  const wsRef         = useRef(null);
  const sessionId     = useRef(Date.now().toString(36));
  const studySetId    = useRef(null);
  const messagesEnd   = useRef(null);
  const textareaRef   = useRef(null);
  const fileInputRef  = useRef(null);
  const chatFileRef   = useRef(null);

  const connect = useCallback(() => {
    const proto  = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsBase = API.replace(/^https?/, proto);
    const ws     = new WebSocket(`${wsBase}/ws/${sessionId.current}`);

    ws.onopen  = () => setConnected(true);
    ws.onclose = () => { setConnected(false); wsRef.current = null; };
    ws.onerror = () => setConnected(false);

    ws.onmessage = (ev) => {
      let frame;
      try { frame = JSON.parse(ev.data); } catch { return; }

      if (frame.type === 'session') {
        studySetId.current = frame.study_set_id;
      } else if (frame.type === 'token') {
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.role === 'ai' && last?.streaming) {
            return [...prev.slice(0, -1), { ...last, text: last.text + frame.content }];
          }
          return [...prev, { role: 'ai', text: frame.content, streaming: true }];
        });
      } else if (frame.type === 'agent_switch') {
        setActiveAgent(frame.agent);
        setMessages(prev => {
          const last = prev[prev.length - 1];
          return last?.streaming
            ? [...prev.slice(0, -1), { ...last, streaming: false }]
            : prev;
        });
      }
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => () => wsRef.current?.close(), []);

  function handleStart() {
    setView('chat');
    connect();
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f?.type === 'application/pdf') setFile(f);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setMessages(prev => [...prev, { role: 'user', text }]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    if (file && studySetId.current) {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('study_set_id', studySetId.current);
      fetch(`${API}/ingest/pdf`, { method: 'POST', body: fd }).catch(() => {});
      setFile(null);
    }

    wsRef.current.send(JSON.stringify({ message: text }));
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function onTextChange(e) {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
  }

  // ── Upload screen ──────────────────────────────────────────────────────────

  if (view === 'upload') {
    return (
      <div className="upload-screen">
        <header className="upload-header">
          <div className="brand">
            <HexIcon size={34} />
            <span className="brand-name">EduHive</span>
          </div>
          <div className="status-pill offline">
            <span className="dot" />
            <span>Offline</span>
          </div>
        </header>

        <main className="upload-main">
          <div className="upload-hero">
            <h1 className="hero-title">
              Upload your materials,<br />
              <span className="hero-accent">start learning.</span>
            </h1>
            <p className="hero-sub">
              Drop a PDF and EduHive's agents will teach, quiz, and guide you through it.
            </p>
          </div>

          <div
            className={`drop-zone${dragOver ? ' drag-over' : ''}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            role="button"
            tabIndex={0}
            aria-label="Upload PDF"
            onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
          >
            <HexIcon size={68} />

            {file ? (
              <div className="file-pill">
                <span>📎 {file.name}</span>
                <button
                  className="remove-file"
                  onClick={(e) => { e.stopPropagation(); setFile(null); }}
                  aria-label="Remove file"
                >✕</button>
              </div>
            ) : (
              <>
                <p className="drop-title">Drop your PDF here</p>
                <p className="drop-sub">or click to select · optional</p>
              </>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              hidden
              onChange={(e) => { const f = e.target.files[0]; if (f) setFile(f); }}
            />
          </div>

          <button className="start-btn" onClick={handleStart}>
            Start Learning <span aria-hidden="true">→</span>
          </button>

          <div className="agent-chips">
            {AGENTS.map(a => (
              <div key={a.key} className="agent-chip">
                <span>{a.icon}</span>
                <span>{a.label}</span>
              </div>
            ))}
          </div>
        </main>
      </div>
    );
  }

  // ── Chat screen ────────────────────────────────────────────────────────────

  return (
    <div className="chat-shell">
      <aside className="sidebar">
        <div className="brand">
          <HexIcon size={30} />
          <span className="brand-name">EduHive</span>
        </div>

        <nav className="agent-list" aria-label="Agents">
          {AGENTS.map(a => (
            <div key={a.key} className={`agent-item${activeAgent === a.key ? ' active' : ''}`}>
              <span className="agent-item-icon">{a.icon}</span>
              <span>{a.label}</span>
              {activeAgent === a.key && <span className="active-dot" />}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className={`status-pill${connected ? ' online' : ' offline'}`}>
            <span className="dot" />
            <span>{connected ? 'Connected' : 'Connecting…'}</span>
          </div>
        </div>
      </aside>

      <main className="chat-main">
        {activeAgent && (
          <div className="agent-bar" role="status">
            {AGENT_LABEL[activeAgent] ?? activeAgent}
          </div>
        )}

        <div className="messages" aria-live="polite">
          {messages.length === 0 && (
            <div className="welcome">
              <HexIcon size={64} />
              <h2>What do you want to learn today?</h2>
              <p>Type your first message below. Your agents are ready.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg msg-${m.role}`}>
              <div className="msg-body">{m.text}</div>
            </div>
          ))}
          <div ref={messagesEnd} />
        </div>

        <form
          className="input-area"
          onSubmit={(e) => { e.preventDefault(); handleSend(); }}
        >
          {file && (
            <div className="attachment-row">
              <span className="attachment-pill">📎 {file.name}</span>
              <button
                type="button"
                className="remove-file-btn"
                onClick={() => setFile(null)}
              >✕</button>
            </div>
          )}

          <div className="input-row">
            <label className="clip-btn" title="Attach PDF">
              <input
                ref={chatFileRef}
                type="file"
                accept=".pdf"
                hidden
                onChange={(e) => { const f = e.target.files[0]; if (f) setFile(f); }}
              />
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
              </svg>
            </label>

            <textarea
              ref={textareaRef}
              value={input}
              onChange={onTextChange}
              onKeyDown={onKeyDown}
              placeholder="Ask anything…"
              rows={1}
              aria-label="Message"
            />

            <button type="submit" className="send-btn" aria-label="Send">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
