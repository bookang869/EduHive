const sessionInput = document.getElementById("session-id");
const clientInput = document.getElementById("client-id");
const connectBtn = document.getElementById("connect-btn");
const disconnectBtn = document.getElementById("disconnect-btn");
const statusPill = document.getElementById("status-pill");
const statusText = document.getElementById("status-text");
const logEl = document.getElementById("log");
const sendForm = document.getElementById("send-form");
const messageInput = document.getElementById("message");

let socket;

const makeSessionId = () => `${Date.now().toString(36)}`;
const makeClientId = () => `${Math.random().toString(36).slice(2, 8)}`;

const setStatus = (state, detail) => {
  statusPill.classList.remove("online", "offline");
  statusPill.classList.add(state === "online" ? "online" : "offline");
  statusText.textContent = state === "online" ? "Connected" : "Disconnected";
  if (detail) {
    statusText.textContent += ` · ${detail}`;
  }
};

const log = (text, tone = "meta", speaker) => {
  const line = document.createElement("div");
  line.className = "log-line";

  const now = new Date().toLocaleTimeString();
  const meta = document.createElement("div");
  meta.className = "log-meta";
  meta.textContent = now;

  const body = document.createElement("div");
  body.textContent = speaker ? `${speaker}: ${text}` : text;
  if (tone === "user") body.classList.add("log-user");
  if (tone === "server") body.classList.add("log-server");

  line.appendChild(meta);
  line.appendChild(body);
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
};

const connect = () => {
  const sessionId = (sessionInput.value || "").trim() || makeSessionId();
  sessionInput.value = sessionId;
  const clientId = (clientInput.value || "").trim() || makeClientId();
  clientInput.value = clientId;

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${location.host}/ws/${encodeURIComponent(
    sessionId
  )}?client_id=${encodeURIComponent(clientId)}`;

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.close();
  }

  socket = new WebSocket(url);
  log(`Connecting to ${url}...`);

  socket.onopen = () => {
    setStatus("online", `${sessionId} · ${clientId}`);
    log(`Connected on session ${sessionId}`, "server");
  };

  socket.onmessage = (event) => {
    log(event.data, "server");
  };

  socket.onclose = () => {
    setStatus("offline");
    log("Connection closed");
  };

  socket.onerror = (error) => {
    setStatus("offline");
    log("WebSocket error. Check server availability.", "server");
    console.error(error);
  };
};

const disconnect = () => {
  if (socket) {
    socket.close();
    socket = null;
  }
  setStatus("offline");
  log("Disconnected by user");
};

connectBtn.addEventListener("click", connect);
disconnectBtn.addEventListener("click", disconnect);

sendForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    log("Connect first to send messages.", "server");
    return;
  }
  socket.send(message);
  const speaker = (clientInput.value || "").trim() || "User";
  log(message, "user", speaker);
  messageInput.value = "";
  messageInput.focus();
});

// Prefill and auto-connect for a fast smoke-test experience
sessionInput.value = makeSessionId();
clientInput.value = makeClientId();
setStatus("offline", `${sessionInput.value} · ${clientInput.value}`);
