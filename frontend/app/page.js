'use client';

import { useState, useRef, useEffect, useCallback, Fragment } from 'react';
import { useSession, signIn, signOut } from 'next-auth/react';
import ReactMarkdown from 'react-markdown';

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

const PIPELINE_STAGES = [
  { key: 'ingestion',  label: 'Ingesting' },
  { key: 'weak_topic', label: 'Analyzing topics' },
  { key: 'study_plan', label: 'Study plan ready' },
];

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
  const { data: session } = useSession();
  const [messages,    setMessages]    = useState([]);
  const [input,       setInput]       = useState('');
  const [connected,   setConnected]   = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const [pipeline,    setPipeline]    = useState({});
  const [file,        setFile]        = useState(null);

  const wsRef          = useRef(null);
  const sessionId      = useRef(Date.now().toString(36));
  const studySetId     = useRef(null);
  const messagesEnd    = useRef(null);
  const textareaRef    = useRef(null);
  const chatFileRef    = useRef(null);
  const pipelineFadeId = useRef(null);

  const wsKey = session?.user?.sub ?? sessionId.current;

  const connect = useCallback(() => {
    studySetId.current = null;
    const proto  = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsBase = API.replace(/^https?/, proto);
    const ws     = new WebSocket(`${wsBase}/ws/${wsKey}`);

    ws.onopen  = () => setConnected(true);
    // ponytail: identity check prevents stale onclose from nulling the live ref (Strict Mode double-mount)
    ws.onclose = () => { setConnected(false); if (wsRef.current === ws) wsRef.current = null; };
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
      } else if (frame.type === 'task_progress') {
        const status = frame.error ? 'error' : (frame.done ? 'done' : 'active');
        setPipeline(prev => ({ ...prev, [frame.stage]: status }));
        if (frame.stage === 'study_plan' && frame.done && !frame.error) {
          clearTimeout(pipelineFadeId.current);
          pipelineFadeId.current = setTimeout(() => setPipeline({}), 3000);
        } else if (frame.error) {
          clearTimeout(pipelineFadeId.current);
          pipelineFadeId.current = setTimeout(() => setPipeline({}), 5000);
        }
      }
    };

    wsRef.current = ws;
  }, [wsKey]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      clearTimeout(pipelineFadeId.current);
    };
  }, [connect]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSend() {
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setMessages(prev => [...prev, { role: 'user', text }]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    if (file) {
      if (!studySetId.current) {
        setMessages(prev => [...prev, { role: 'ai', text: '⚠️ Still connecting — please try again in a moment.' }]);
        return;
      }
      const fd = new FormData();
      fd.append('file', file);
      fd.append('study_set_id', studySetId.current);
      const res = await fetch(`${API}/ingest/pdf`, { method: 'POST', body: fd }).catch(() => null);
      if (res && !res.ok) {
        const { detail } = await res.json().catch(() => ({ detail: 'Upload failed' }));
        setMessages(prev => [...prev, { role: 'ai', text: `⚠️ ${detail}` }]);
        return;
      }
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

  const showPipeline = Object.keys(pipeline).length > 0;

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

          {session ? (
            <div className="auth-user">
              {session.user.image && (
                <img src={session.user.image} alt="" className="auth-avatar" />
              )}
              <span className="auth-name">{session.user.name ?? session.user.email}</span>
              <button className="auth-btn" onClick={() => signOut()}>Out</button>
            </div>
          ) : (
            <button className="auth-btn auth-btn-primary" onClick={() => signIn('google')}>
              Sign in with Google
            </button>
          )}
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
              <div className="msg-body prose">
                {m.role === 'ai'
                  ? <ReactMarkdown>{m.text}</ReactMarkdown>
                  : m.text}
              </div>
            </div>
          ))}
          <div ref={messagesEnd} />
        </div>

        {showPipeline && (
          <div className="pipeline-bar" role="status" aria-label="Background processing">
            {PIPELINE_STAGES.map((s, idx) => {
              const status = pipeline[s.key];
              return (
                <Fragment key={s.key}>
                  <span className={`pipeline-step${status ? ` ${status}` : ''}`}>
                    {status === 'done' ? '✓' : status === 'error' ? '✕' : '●'} {s.label}
                  </span>
                  {idx < PIPELINE_STAGES.length - 1 && (
                    <span className="pipeline-sep">→</span>
                  )}
                </Fragment>
              );
            })}
          </div>
        )}

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
