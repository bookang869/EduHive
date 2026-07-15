'use client';

import { useState, useRef, useEffect, useCallback, Fragment } from 'react';
import { useSession, signIn, signOut } from 'next-auth/react';
import ReactMarkdown from 'react-markdown';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const AGENTS = [
  { key: 'teacher_agent',        label: 'Teacher',  icon: '📖' },
  { key: 'feynman_agent',        label: 'Feynman',  icon: '🧠' },
  { key: 'quiz_agent',           label: 'Quiz',     icon: '✏️' },
  { key: 'classification_agent', label: 'Classify', icon: '🗂️' },
];

const AGENT_LABEL = {
  classification_agent: 'ASSESSING',
  teacher_agent:        'TEACHING',
  feynman_agent:        'FEYNMAN',
  quiz_agent:           'QUIZ',
};

const PIPELINE_STAGES = [
  { key: 'ingestion',  label: 'Ingesting' },
  { key: 'weak_topic', label: 'Analyzing topics' },
  { key: 'study_plan', label: 'Study plan ready' },
];

const STEPS = [
  { n: '01', label: 'Start' },
  { n: '02', label: 'Analyze' },
  { n: '03', label: 'Study' },
  { n: '04', label: 'Summary' },
];

const AGENT_CARDS = [
  { category: 'STEP-BY-STEP',  emoji: '🧑‍🏫', title: 'Teacher',    desc: "Breaks concepts into clear explanations tailored to how you think. Your go-to when you're learning something new or need it explained differently." },
  { category: 'ACTIVE RECALL', emoji: '🔬',    title: 'Feynman',    desc: "Asks you to explain things back in your own words. Pinpoints exactly where your understanding breaks down and guides you to fill the gap." },
  { category: 'PRACTICE',      emoji: '📋',    title: 'Quiz',       desc: "Generates targeted questions from your materials. Tracks what you've mastered and surfaces what still needs work — with every attempt scored." },
  { category: 'SMART ROUTING', emoji: '🎯',    title: 'Classifier', desc: "Reads your intent and routes each message to the right expert automatically. You just ask — it figures out who should answer." },
];

const PROBLEMS = [
  { icon: '📖', title: 'You read, but nothing sticks',        desc: 'Passive reading creates the illusion of learning. Without active recall, most information fades within 24 hours.' },
  { icon: '❓', title: "You don't know what you don't know",  desc: "Textbooks can't reveal which topics you've actually mastered versus which ones you've only skimmed the surface of." },
  { icon: '🔁', title: 'No feedback loop',                    desc: 'Studying without being tested is guessing in the dark. You need something that pushes back and reveals your real gaps.' },
  { icon: '⏳', title: 'Every session starts from zero',       desc: 'Notes get lost, highlights fade, and you re-read the same chapter instead of building on what you already know.' },
];

const HOW_STEPS = [
  { num: '01', title: 'Upload your PDFs',         desc: 'Drop in any study material — textbooks, lecture slides, research papers, notes. Multi-file upload supported.' },
  { num: '02', title: 'AI analyzes your content', desc: 'EduHive chunks, indexes, and maps key concepts. Weak topics are flagged before you even ask your first question.' },
  { num: '03', title: 'Learn with your team',     desc: 'Ask questions, get tailored explanations, take quizzes, and validate your understanding through conversation.' },
  { num: '04', title: 'Reach mastery',            desc: 'Feynman-style challenges reveal exactly what you understand — and what you only think you do. Fill every gap.' },
];

const FEATURES = [
  { icon: '💬', title: 'Real-time streaming',    desc: 'Responses stream token by token for a natural, conversational feel.' },
  { icon: '📄', title: 'PDF ingestion',          desc: 'Multi-file upload. Any length. Chunk-level retrieval for precise, grounded answers.' },
  { icon: '🗺️', title: 'Topic mapping',          desc: 'Automatic identification of key concepts and likely weak areas from your materials.' },
  { icon: '📖', title: 'Study guide',            desc: 'A generated overview of your content with key takeaways, ready to read or share.' },
  { icon: '🃏', title: 'Flashcards',             desc: 'Auto-generated cards from your PDFs — ready for spaced repetition practice.' },
  { icon: '✏️', title: 'Quizzes & scoring',      desc: 'Questions generated from your materials, scored and tracked across every session.' },
  { icon: '🧠', title: 'Feynman validation',     desc: 'Challenges you to explain concepts back in your own words to confirm real understanding.' },
  { icon: '💾', title: 'Session memory',         desc: 'Pick up exactly where you left off. Your study set and progress persist between sessions.' },
];

function TopNav({ activeStep, isLanding, connected, showStatus, onSignOut, onLogoClick }) {
  return (
    <header className="top-nav">
      <div className="nav-brand" onClick={onLogoClick} style={{ cursor: onLogoClick ? 'pointer' : 'default' }}>
        <div className="nav-logo">E</div>
        <span className="nav-brand-name">EduHive</span>
      </div>
      {isLanding ? (
        <nav className="nav-anchors" aria-label="Sections">
          <a href="#agents"       className="nav-anchor">Agents</a>
          <a href="#how-it-works" className="nav-anchor">How it works</a>
          <a href="#features"     className="nav-anchor">Features</a>
        </nav>
      ) : (
        <nav className="nav-steps" aria-label="Progress">
          {STEPS.map((s, i) => (
            <span
              key={s.n}
              className={`nav-step${i === activeStep ? ' active' : ''}${i < activeStep ? ' done' : ''}`}
            >
              {s.n}·{s.label}
            </span>
          ))}
        </nav>
      )}
      <div className={`nav-status${showStatus ? (connected ? ' online' : ' offline') : ''}`}>
        {isLanding && (
          <a href="#intro" className="btn-cta nav-cta">Start free →</a>
        )}
        {!isLanding && showStatus && <span className="nav-dot" />}
        {!isLanding && showStatus && <span>{connected ? 'Connected' : 'Connecting…'}</span>}
        {onSignOut && (
          <button className="nav-signout" onClick={onSignOut}>Sign out</button>
        )}
      </div>
    </header>
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

  const [messages,       setMessages]       = useState([]);
  const [input,          setInput]          = useState('');
  const [connected,      setConnected]      = useState(false);
  const [activeAgent,    setActiveAgent]    = useState(null);
  const [pipeline,       setPipeline]       = useState({});
  const [studyMaterials, setStudyMaterials] = useState(null);
  const [quizAttempts,   setQuizAttempts]   = useState([]);
  const [showGuide,      setShowGuide]      = useState(false);
  const [restoredSid,    setRestoredSid]    = useState(null);

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

  // Restore study_set_id from localStorage on mount
  useEffect(() => {
    const sid = localStorage.getItem('eduhive_sid');
    if (sid) { studySetId.current = sid; setRestoredSid(sid); }
  }, []);

  // Fetch study materials once study_plan pipeline is done
  useEffect(() => {
    const sid = studySetId.current;
    if (!sid || pipeline.study_plan !== 'done') return;
    fetch(`${API}/study-materials/${sid}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStudyMaterials(d); })
      .catch(() => null);
  }, [pipeline.study_plan]);

  // Fetch previous quiz attempts when entering chat
  useEffect(() => {
    const sid = studySetId.current;
    if (phase !== 'chat' || !sid) return;
    fetch(`${API}/quiz-attempts/${sid}`)
      .then(r => r.ok ? r.json() : [])
      .then(d => setQuizAttempts(d))
      .catch(() => null);
  }, [phase]);

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
        localStorage.setItem('eduhive_sid', sid);
        setRestoredSid(sid);
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
      <div className="signin-screen">
        <div className="signin-logo">E</div>
      </div>
    );
  }

  // ── Sign-in ───────────────────────────────────────────────────────────────

  if (!session) {
    return (
      <div className="signin-screen">
        <div className="signin-logo">E</div>
        <h1 className="signin-title">EduHive</h1>
        <p className="signin-sub">Your AI tutoring co-pilot</p>
        <button className="google-btn" onClick={() => signIn('google')}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
          </svg>
          Continue with Google
        </button>
      </div>
    );
  }

  // ── Upload (landing page) ─────────────────────────────────────────────────

  if (phase === 'upload') {
    const dragProps = {
      onDragOver:  e => { e.preventDefault(); setIsDragOver(true); },
      onDragLeave: () => setIsDragOver(false),
      onDrop:      e => { e.preventDefault(); setIsDragOver(false); addFiles(e.dataTransfer.files); },
    };

    const UploadCard = ({ style }) => (
      <div className={`upload-card${isDragOver ? ' drag-over' : ''}`} {...dragProps} style={style}>
        <div className="upload-icon-wrap">📄</div>
        <p className="upload-title">
          {studySetId.current ? 'Add more PDFs to your session' : 'Drop your PDF here'}
        </p>
        <p className="upload-hint">or click to select · PDF only</p>
        <div className="upload-btns">
          <label style={{ cursor: 'pointer' }}>
            <input type="file" accept=".pdf" multiple hidden onChange={e => addFiles(e.target.files)} />
            <span className="btn-primary">Browse files</span>
          </label>
          <button className="btn-alt" disabled={!stagedFiles.length} onClick={startLearning}>
            Learn →
          </button>
        </div>
      </div>
    );

    return (
      <>
        <TopNav isLanding={true} connected={false} showStatus={false} onSignOut={() => signOut()} />

        {/* ─── Hero ──────────────────────────────────────────────────────── */}
        <div className="page" id="intro">
          <div className="landing">
            <div className="landing-badge">
              <span className="badge-dot" />
              EduHive · Beta
            </div>

            <h1 className="landing-hero">
              Upload your materials,<br />
              get a <span className="hero-accent">full AI tutor team</span>.
            </h1>

            <p className="landing-sub">
              Four specialized agents teach, quiz, and challenge you<br />
              until you truly understand — whatever you're studying.
            </p>

            <UploadCard />

            {stagedFiles.length > 0 && (
              <div className="staged-files">
                {stagedFiles.map((f, i) => (
                  <span key={f.name} className="staged-pill">
                    📄 {f.name}
                    <button onClick={() => setStagedFiles(prev => prev.filter((_, j) => j !== i))}>✕</button>
                  </span>
                ))}
              </div>
            )}

            {ingestError && <p className="error-msg">{ingestError}</p>}

            {restoredSid && (
              <button className="text-link" onClick={() => enterChat(restoredSid)}>
                ← Resume session
              </button>
            )}

            <div className="hero-pills">
              <span className="hero-pill">4 Specialized Agents</span>
              <span className="hero-pill">Feynman Method</span>
              <span className="hero-pill">Auto Study Plans</span>
              <span className="hero-pill">PDF Upload</span>
            </div>
          </div>
        </div>

        {/* ─── Problem ───────────────────────────────────────────────────── */}
        <section className="lp-section">
          <p className="section-eyebrow">The problem</p>
          <h2 className="section-heading">
            Studying alone<br />is <span className="hero-accent">broken</span>.
          </h2>
          <div className="two-col-grid">
            {PROBLEMS.map(p => (
              <div key={p.title} className="problem-card">
                <div className="problem-icon">{p.icon}</div>
                <h3>{p.title}</h3>
                <p>{p.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ─── Agents ────────────────────────────────────────────────────── */}
        <section className="lp-section lp-section--bordered" id="agents">
          <p className="section-eyebrow">Meet your tutor team</p>
          <h2 className="section-heading">
            Four agents, one goal:<br />make you <span className="hero-accent">truly understand</span>.
          </h2>
          <div className="persona-grid">
            {AGENT_CARDS.map(a => (
              <div key={a.title} className="persona-card">
                <span className="persona-category">{a.category}</span>
                <div className="persona-illustration">{a.emoji}</div>
                <h3>{a.title}</h3>
                <p>{a.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ─── How it works ──────────────────────────────────────────────── */}
        <section className="lp-section lp-section--bordered" id="how-it-works">
          <p className="section-eyebrow">How it works</p>
          <h2 className="section-heading">
            From upload to mastery<br />in <span className="hero-accent">four steps</span>.
          </h2>
          <div className="four-col-grid">
            {HOW_STEPS.map(s => (
              <div key={s.num} className="step-card">
                <span className="step-num">{s.num}</span>
                <h3>{s.title}</h3>
                <p>{s.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ─── Features ──────────────────────────────────────────────────── */}
        <section className="lp-section lp-section--bordered" id="features">
          <p className="section-eyebrow">What's included</p>
          <h2 className="section-heading">
            Everything you need.<br /><span className="hero-accent">Nothing you don't</span>.
          </h2>
          <div className="features-grid">
            {FEATURES.map(f => (
              <div key={f.title} className="feature-card">
                <span className="feature-icon">{f.icon}</span>
                <h4>{f.title}</h4>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </section>

      </>
    );
  }

  // ── Ingesting (Analyze) ───────────────────────────────────────────────────

  if (phase === 'ingesting') {
    const uploadsDone = ingestProgress.done >= ingestProgress.total && ingestProgress.total > 0;
    const pct = uploadsDone
      ? 100
      : Math.round((ingestProgress.done / Math.max(ingestProgress.total, 1)) * 100);

    return (
      <>
        <TopNav activeStep={1} connected={false} showStatus={false} onLogoClick={() => { clearInterval(pollRef.current); setPhase('upload'); }} />
        <div className="page">
          <div className="analyze-screen">
            <div className="landing-badge">
              <span className="badge-dot" />
              {uploadsDone ? 'Building your study plan' : `Uploading ${ingestProgress.done + 1} of ${ingestProgress.total}`}
            </div>
            <h1 className="landing-hero" style={{ fontSize: 'clamp(1.8rem, 4vw, 2.8rem)' }}>
              {uploadsDone
                ? <>Building your <span className="hero-accent">study plan</span>…</>
                : <>Uploading your <span className="hero-accent">materials</span>…</>}
            </h1>
            <p className="landing-sub" style={{ marginBottom: 0 }}>
              This usually takes under a minute.
            </p>
            <div className="progress-wrap">
              <div className="progress-track">
                <div
                  className={`progress-bar${uploadsDone ? ' pulse' : ''}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </>
    );
  }

  // ── Chat ──────────────────────────────────────────────────────────────────

  const showPipeline = Object.keys(pipeline).length > 0;

  return (
    <>
      <TopNav activeStep={2} connected={connected} showStatus={true} onLogoClick={() => { wsRef.current?.close(); setPhase('upload'); }} />
      {showGuide && studyMaterials?.guide && (
        <div className="guide-overlay" onClick={() => setShowGuide(false)}>
          <div className="guide-panel" onClick={e => e.stopPropagation()}>
            <div className="guide-header">
              <span>Study Guide</span>
              <button className="guide-close" onClick={() => setShowGuide(false)}>✕</button>
            </div>
            <div className="guide-body prose">
              <ReactMarkdown>{studyMaterials.guide}</ReactMarkdown>
            </div>
          </div>
        </div>
      )}
      <div className="chat-shell">
        <aside className="sidebar">
          <p className="sidebar-label">Agents</p>
          <nav className="agent-list" aria-label="Agents">
            {AGENTS.map(a => (
              <div key={a.key} className={`agent-item${activeAgent === a.key ? ' active' : ''}`}>
                <span style={{ fontSize: 15 }}>{a.icon}</span>
                <span>{a.label}</span>
                {activeAgent === a.key && <span className="active-dot" />}
              </div>
            ))}
          </nav>

          {studyMaterials && (
            <>
              <p className="sidebar-label">Study Materials</p>
              <div className="materials-list">
                {studyMaterials.guide && (
                  <button className="materials-item" onClick={() => setShowGuide(true)}>
                    📖 Study Guide
                  </button>
                )}
                {studyMaterials.flashcards?.length > 0 && (
                  <div className="materials-item">
                    🃏 Flashcards ({studyMaterials.flashcards.length})
                  </div>
                )}
                {studyMaterials.questions?.length > 0 && (
                  <div className="materials-item">
                    ✏️ Quiz ({studyMaterials.questions.length} questions)
                  </div>
                )}
              </div>
            </>
          )}

          {quizAttempts.length > 0 && (
            <>
              <p className="sidebar-label">Recent Scores</p>
              <div className="attempts-list">
                {quizAttempts.slice(0, 3).map(a => (
                  <div key={a.id} className="attempt-row">
                    <span className="attempt-score">{a.score}</span>
                    <span className="attempt-date">{new Date(a.taken_at).toLocaleDateString()}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="sidebar-footer">
            <button
              className="sidebar-btn"
              onClick={() => { wsRef.current?.close(); setPhase('upload'); }}
            >
              + Add PDF
            </button>
            <div className="auth-user">
              {session.user.image && (
                <img src={session.user.image} alt="" className="auth-avatar" />
              )}
              <span className="auth-name">{session.user.name ?? session.user.email}</span>
              <button className="sidebar-btn-ghost" onClick={() => signOut()}>Out</button>
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
                <div className="welcome-icon">📚</div>
                <h2>Your materials are ready!</h2>
                <p>Ask me anything about what you uploaded.<br />I can teach, quiz, or guide you.</p>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg msg-${m.role}`}>
                <div className={`msg-body${m.role === 'ai' ? ' prose' : ''}`}>
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
                placeholder="Ask anything about your materials…"
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
    </>
  );
}
