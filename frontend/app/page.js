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
  return (
    <div style={{
      width: size, height: size, flexShrink: 0, position: 'relative',
      background: 'linear-gradient(135deg, #f6c454, #f59e0b)',
      clipPath: 'polygon(25% 6.7%, 75% 6.7%, 100% 50%, 75% 93.3%, 25% 93.3%, 0% 50%)',
      boxShadow: '0 8px 24px rgba(245,158,11,0.28)',
    }}>
      <div style={{
        position: 'absolute', inset: '18%',
        background: 'var(--panel)',
        clipPath: 'polygon(25% 6.7%, 75% 6.7%, 100% 50%, 75% 93.3%, 25% 93.3%, 0% 50%)',
      }} />
    </div>
  );
}

export default function Page() {
  const { data: session, status: authStatus } = useSession();

  // 'upload' | 'ingesting' | 'chat'
  const [phase,          setPhase]          = useState('upload');
  const [stagedFiles,    setStagedFiles]    = useState([]);
  const [isDragOver,     setIsDragOver]     = useState(false);
  const [ingestProgress, setIngestProgress] = useState({ done: 0, total: 0 });
  const [ingestError,    setIngestError]    = useState(null);

  const [messages,    setMessages]    = useState([]);
  const [input,       setInput]       = useState('');
  const [connected,   setConnected]   = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const [pipeline,    setPipeline]    = useState({});

  const wsRef          = useRef(null);
  const sessionId      = useRef(Date.now().toString(36));
  const studySetId     = useRef(null);
  const messagesEnd    = useRef(null);
  const textareaRef    = useRef(null);
  const pipelineFadeId = useRef(null);
  const pollRef        = useRef(null);

  const wsKey = session?.user?.sub ?? sessionId.current;
  const token = session?.backendToken;

  const connect = useCallback((sid) => {
    const proto  = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsBase = API.replace(/^https?/, proto);
    const params = new URLSearchParams();
    if (sid) params.set('study_set_id', sid);
    if (token) params.set('token', token);
    const qs = params.toString();
    const ws = new WebSocket(`${wsBase}/ws/${wsKey}${qs ? `?${qs}` : ''}`);

    ws.onopen  = () => setConnected(true);
    ws.onclose = () => { setConnected(false); if (wsRef.current === ws) wsRef.current = null; };
    ws.onerror = () => setConnected(false);

    ws.onmessage = (ev) => {
      let frame;
      try { frame = JSON.parse(ev.data); } catch { return; }

      if (frame.type === 'token') {
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
  }, [wsKey, token]);

  const enterChat = useCallback((sid) => {
    clearInterval(pollRef.current);
    setPhase('chat');
    connect(sid ?? studySetId.current);
  }, [connect]);

  useEffect(() => () => {
    wsRef.current?.close();
    clearInterval(pollRef.current);
    clearTimeout(pipelineFadeId.current);
  }, []);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function addFiles(newFiles) {
    setStagedFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...[...newFiles].filter(f => f.name.endsWith('.pdf') && !names.has(f.name))];
    });
  }

  async function startLearning() {
    if (!stagedFiles.length) return;
    const isMidSession = !!studySetId.current;
    setPhase('ingesting');
    setIngestError(null);
    setIngestProgress({ done: 0, total: stagedFiles.length });

    let sid = studySetId.current;

    for (let i = 0; i < stagedFiles.length; i++) {
      const fd = new FormData();
      fd.append('file', stagedFiles[i]);
      if (sid) fd.append('study_set_id', sid);

      const res = await fetch(`${API}/ingest/pdf`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token ?? ''}` },
        body: fd,
      }).catch(() => null);

      if (!res?.ok) {
        const { detail } = await res?.json().catch(() => ({})) ?? {};
        setIngestError(detail ?? 'Upload failed');
        setPhase('upload');
        return;
      }

      const data = await res.json();
      if (!sid) {
        sid = data.study_set_id;
        studySetId.current = sid;
      }
      setIngestProgress({ done: i + 1, total: stagedFiles.length });
    }

    setStagedFiles([]);

    if (isMidSession) {
      await fetch(`${API}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token ?? ''}` },
        body: JSON.stringify({ study_set_id: sid }),
      }).catch(() => null);
    }

    pollRef.current = setInterval(async () => {
      const r = await fetch(`${API}/ingest/status?study_set_id=${sid}`).catch(() => null);
      if (!r?.ok) return;
      const { status } = await r.json().catch(() => ({}));
      if (status === 'complete') enterChat(sid);
    }, 2000);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setMessages(prev => [...prev, { role: 'user', text }]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    wsRef.current.send(JSON.stringify({ message: text }));
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  function onTextChange(e) {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
  }

  // ── Auth loading ──────────────────────────────────────────────────────────

  if (authStatus === 'loading') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100svh' }}>
        <HexIcon size={48} />
      </div>
    );
  }

  // ── Sign-in screen ────────────────────────────────────────────────────────

  if (!session) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100svh', gap: '1.5rem' }}>
        <HexIcon size={64} />
        <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.03em' }}>EduHive</h1>
        <p style={{ margin: 0, color: 'var(--muted)' }}>Your AI tutoring co-pilot</p>
        <button
          className="auth-btn-primary"
          style={{ width: 'auto', margin: 0, padding: '0.75rem 2rem', fontSize: '1rem', borderRadius: 10 }}
          onClick={() => signIn('google')}
        >
          Sign in with Google
        </button>
      </div>
    );
  }

  // ── Upload / Ingesting screen ─────────────────────────────────────────────

  if (phase === 'upload' || phase === 'ingesting') {
    const isIngesting = phase === 'ingesting';
    const uploadsDone = ingestProgress.done >= ingestProgress.total && ingestProgress.total > 0;

    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100svh', gap: '1.25rem', padding: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
          <HexIcon size={32} />
          <span style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '-0.03em' }}>EduHive</span>
        </div>

        {/* Drop zone */}
        <div
          style={{
            width: '100%', maxWidth: 520,
            border: `2px dashed ${isDragOver ? 'var(--accent)' : 'var(--border)'}`,
            borderRadius: 16, padding: '2.5rem 2rem', textAlign: 'center',
            background: isDragOver ? 'rgba(246,196,84,0.04)' : 'var(--panel)',
            transition: 'all 0.15s',
            opacity: isIngesting ? 0.5 : 1,
            pointerEvents: isIngesting ? 'none' : 'auto',
          }}
          onDragOver={e => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={e => { e.preventDefault(); setIsDragOver(false); addFiles(e.dataTransfer.files); }}
        >
          <p style={{ margin: '0 0 0.4rem', fontWeight: 700, fontSize: '1.05rem' }}>
            {studySetId.current ? 'Add more PDFs' : 'Upload your study materials'}
          </p>
          <p style={{ margin: '0 0 1.25rem', color: 'var(--muted)', fontSize: '0.875rem' }}>
            Drag & drop PDFs here, or click to browse
          </p>
          <label style={{ cursor: 'pointer' }}>
            <input type="file" accept=".pdf" multiple hidden onChange={e => addFiles(e.target.files)} />
            <span className="auth-btn" style={{ display: 'inline-block', padding: '6px 18px', fontSize: '13px' }}>
              Browse files
            </span>
          </label>
        </div>

        {/* Staged file pills */}
        {stagedFiles.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', maxWidth: 520, width: '100%' }}>
            {stagedFiles.map((f, i) => (
              <span key={f.name} style={{
                display: 'flex', alignItems: 'center', gap: '0.4rem',
                background: 'var(--panel)', border: '1px solid var(--border)',
                borderRadius: 999, padding: '4px 12px', fontSize: '12px', color: 'var(--muted)',
              }}>
                📄 {f.name}
                {!isIngesting && (
                  <button
                    onClick={() => setStagedFiles(prev => prev.filter((_, j) => j !== i))}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', lineHeight: 1, padding: 0, fontFamily: 'inherit' }}
                  >✕</button>
                )}
              </span>
            ))}
          </div>
        )}

        {/* Error */}
        {ingestError && (
          <p style={{ color: '#ff7b72', margin: 0, fontSize: '0.875rem' }}>{ingestError}</p>
        )}

        {/* Progress or CTA */}
        {isIngesting ? (
          <div style={{ textAlign: 'center', maxWidth: 520, width: '100%' }}>
            <p style={{ color: 'var(--muted)', fontSize: '0.875rem', marginBottom: '0.75rem' }}>
              {!uploadsDone
                ? `Uploading ${ingestProgress.done + 1} of ${ingestProgress.total}…`
                : 'Processing your materials…'}
            </p>
            <div style={{ height: 6, background: 'var(--border)', borderRadius: 999, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 999,
                background: 'linear-gradient(90deg, #f6c454, #f59e0b)',
                width: uploadsDone ? '100%' : `${Math.round((ingestProgress.done / ingestProgress.total) * 100)}%`,
                animation: uploadsDone ? 'pulse 1.5s ease-in-out infinite' : 'none',
                transition: 'width 0.3s ease',
              }} />
            </div>
          </div>
        ) : (
          <button
            className="auth-btn-primary"
            style={{ width: 'auto', margin: 0, padding: '10px 2.5rem', fontSize: '0.95rem', opacity: stagedFiles.length ? 1 : 0.4 }}
            disabled={!stagedFiles.length}
            onClick={startLearning}
          >
            {studySetId.current ? 'Add to session' : 'Start Learning'}
          </button>
        )}

        {/* Footer link */}
        {!isIngesting && (
          <button
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: '0.8rem', fontFamily: 'inherit' }}
            onClick={() => studySetId.current ? enterChat(studySetId.current) : signOut()}
          >
            {studySetId.current ? '← Back to chat' : 'Sign out'}
          </button>
        )}
      </div>
    );
  }

  // ── Chat screen ───────────────────────────────────────────────────────────

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

          <button
            className="auth-btn-primary"
            onClick={() => { wsRef.current?.close(); setPhase('upload'); }}
          >
            + Add PDF
          </button>

          <div className="auth-user">
            {session.user.image && (
              <img src={session.user.image} alt="" className="auth-avatar" />
            )}
            <span className="auth-name">{session.user.name ?? session.user.email}</span>
            <button className="auth-btn" onClick={() => signOut()}>Out</button>
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
              <h2>Your materials are ready!</h2>
              <p>Ask me anything about what you uploaded.</p>
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
          <div className="input-row">
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
