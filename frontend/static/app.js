// --- DOM refs ---
const statusPill   = document.getElementById("status-pill");
const statusText   = document.getElementById("status-text");
const messagesEl   = document.getElementById("messages");
const sendForm     = document.getElementById("send-form");
const messageInput = document.getElementById("message");
const pdfInput     = document.getElementById("pdf-input");
const attachRow    = document.getElementById("attachment-row");
const attachPill   = document.getElementById("attachment-pill");
const removeBtn    = document.getElementById("remove-attachment");
const agentBar     = document.getElementById("agent-bar");
const agentLabel   = document.getElementById("agent-label");
const pipelineBar  = document.getElementById("pipeline-bar");
const pipelineCheck= document.getElementById("pipeline-check");

const AGENT_LABELS = {
  classification_agent: "Assessing…",
  teacher_agent:        "Teaching…",
  feynman_agent:        "Feynman…",
  quiz_agent:           "Quiz…",
};

const STAGE_DONE = {};  // tracks which stages are complete

let socket;
let studySetId = null;
let sessionId  = `${Date.now().toString(36)}`;
let currentBubble = null;  // AI message bubble being streamed

// --- Status helpers ---
const setStatus = (state, detail) => {
  statusPill.classList.toggle("online", state === "online");
  statusPill.classList.toggle("offline", state !== "online");
  statusText.textContent = state === "online" ? `Connected · ${detail}` : "Disconnected";
};

// --- Message rendering ---
function addMessage(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `msg msg-${role}`;
  const body = document.createElement("div");
  body.className = "msg-body";
  body.textContent = text;
  wrap.appendChild(body);
  // remove welcome screen on first message
  const welcome = messagesEl.querySelector(".welcome");
  if (welcome) welcome.remove();
  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return body;
}

function startAIBubble() {
  currentBubble = addMessage("ai", "");
  return currentBubble;
}

function appendToken(text) {
  if (!currentBubble) startAIBubble();
  currentBubble.textContent += text;
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function finalizeAIBubble() {
  currentBubble = null;
}

// --- Agent label ---
function setAgent(name) {
  const label = AGENT_LABELS[name] || name;
  agentLabel.textContent = label;
  agentBar.style.display = "block";
}

// --- Pipeline progress ---
function updatePipeline(stage, done) {
  pipelineBar.style.display = "flex";
  const el = document.getElementById(`stage-${stage}`);
  if (el) {
    el.classList.toggle("stage-done", done);
    el.classList.toggle("stage-active", !done);
  }
  STAGE_DONE[stage] = done;
  if (done && stage === "weak_topic") {
    pipelineCheck.style.display = "inline";
  }
}

// --- WebSocket ---
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/${encodeURIComponent(sessionId)}`;

  if (socket && socket.readyState === WebSocket.OPEN) socket.close();
  socket = new WebSocket(url);

  socket.onopen = () => setStatus("online", sessionId);
  socket.onclose = () => setStatus("offline");
  socket.onerror = () => setStatus("offline");

  socket.onmessage = (ev) => {
    let frame;
    try { frame = JSON.parse(ev.data); } catch { return; }

    switch (frame.type) {
      case "session":
        studySetId = frame.study_set_id;
        break;
      case "token":
        appendToken(frame.content);
        break;
      case "agent_switch":
        if (currentBubble) finalizeAIBubble();
        setAgent(frame.agent);
        break;
      case "task_progress":
        updatePipeline(frame.stage, frame.done);
        break;
    }
  };
}

// auto-connect on load
connect();

// --- PDF attachment ---
pdfInput.addEventListener("change", () => {
  const file = pdfInput.files[0];
  if (!file) return;
  attachPill.textContent = `📎 ${file.name}`;
  attachRow.style.display = "flex";
});

removeBtn.addEventListener("click", () => {
  pdfInput.value = "";
  attachRow.style.display = "none";
});

// --- Send ---
sendForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;

  // ensure connected
  if (!socket || socket.readyState !== WebSocket.OPEN) connect();

  // wait for handshake (studySetId) before uploading PDF
  if (pdfInput.files[0] && !studySetId) {
    await new Promise((resolve) => {
      const check = setInterval(() => { if (studySetId) { clearInterval(check); resolve(); } }, 100);
    });
  }

  addMessage("user", text);
  messageInput.value = "";
  messageInput.style.height = "auto";
  currentBubble = null;

  // upload PDF in parallel with sending the message
  const file = pdfInput.files[0];
  if (file && studySetId) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("study_set_id", studySetId);
    fetch("/ingest/pdf", { method: "POST", body: fd }).catch(console.error);
    pdfInput.value = "";
    attachRow.style.display = "none";
  }

  socket.send(JSON.stringify({ message: text }));
});

// auto-grow textarea
messageInput.addEventListener("input", () => {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + "px";
});

// Enter to send (Shift+Enter for newline)
messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendForm.dispatchEvent(new Event("submit", { cancelable: true }));
  }
});
