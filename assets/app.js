// MVS-Q frontend -- vanilla fetch()/DOM + Socket.IO client, no framework, matching this
// workspace's convention (see progq's/techaq's app.js). Talks to the "state"/"key" protocol
// documented in python/main.py's module docstring; keep this file in sync with that docstring.
//
// There is exactly one shared 3270 session for the whole app (see main.py's docstring) -- every
// open tab sees and drives the same terminal, the same way a second person walking up to a real
// 3270 would.

let socket;
let latestState = { connected: false, rows: [], cursor: { row: 0, col: 0 } };

const ROWS = 24;
const COLS = 80;
const CHAR_W_CH = 1;
const LINE_H_PX = 20;
const PAD_PX = 12;

function sendKey(payload) {
  socket.emit("key", payload);
}

// Printable keystrokes are buffered and flushed as one "text" message instead of one
// socket message per keystroke -- typing fast enough (a quick human, or automated input)
// can otherwise let the per-keystroke HTTP round-trips to the Brick complete out of order
// and scramble the typed text. Control keys (Enter/Tab/PF/Clear) flush the buffer first so
// ordering relative to them is preserved.
let pendingText = "";
let flushTimer = null;

function flushPendingText() {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  if (pendingText) {
    sendKey({ text: pendingText });
    pendingText = "";
  }
}

function queueText(ch) {
  pendingText += ch;
  if (flushTimer) clearTimeout(flushTimer);
  flushTimer = setTimeout(flushPendingText, 80);
}

function sendControl(payload) {
  flushPendingText();
  sendKey(payload);
}

function blankScreen() {
  return Array.from({ length: ROWS }, () => " ".repeat(COLS));
}

function renderScreen(state) {
  const rows = state.rows && state.rows.length ? state.rows : blankScreen();
  document.getElementById("screen").textContent = rows.join("\n");

  const cursor = document.getElementById("cursor");
  cursor.style.display = state.connected ? "block" : "none";
  const row = (state.cursor && state.cursor.row) || 0;
  const col = (state.cursor && state.cursor.col) || 0;
  cursor.style.top = `${PAD_PX + row * LINE_H_PX}px`;
  cursor.style.left = `calc(${PAD_PX}px + ${col * CHAR_W_CH}ch)`;
}

function renderStatus(state) {
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");
  dot.classList.toggle("online", !!state.connected);
  text.textContent = state.connected ? "mainframe online" : "mainframe offline";
}

function onState(state) {
  latestState = state;
  renderScreen(state);
  renderStatus(state);
}

// -- keyboard passthrough --------------------------------------------------------------------
// The terminal wrap must be focused (click it) before keystrokes are captured, so typing
// elsewhere on the page (e.g. into a future control-panel input) doesn't leak into the session.

function isPrintable(key) {
  return key.length === 1;
}

function onTerminalKeydown(evt) {
  if (evt.ctrlKey || evt.metaKey || evt.altKey) return;

  if (evt.key === "Enter") {
    evt.preventDefault();
    sendControl({ enter: true });
    return;
  }
  if (evt.key === "Tab") {
    evt.preventDefault();
    sendControl(evt.shiftKey ? { backtab: true } : { tab: true });
    return;
  }
  const pfMatch = /^F([1-9]|1[0-2])$/.exec(evt.key);
  if (pfMatch) {
    evt.preventDefault();
    const n = Number(pfMatch[1]) + (evt.shiftKey ? 12 : 0);
    sendControl({ pf: n });
    return;
  }
  if (isPrintable(evt.key)) {
    evt.preventDefault();
    queueText(evt.key);
  }
}

function setupTerminal() {
  const wrap = document.getElementById("terminal-wrap");
  wrap.addEventListener("keydown", onTerminalKeydown);
  wrap.addEventListener("click", () => wrap.focus());
}

// -- on-screen key bar -------------------------------------------------------------------------

function setupKeybar() {
  document.getElementById("enter-btn").addEventListener("click", () => sendControl({ enter: true }));
  document.getElementById("tab-btn").addEventListener("click", () => sendControl({ tab: true }));
  document.getElementById("backtab-btn").addEventListener("click", () => sendControl({ backtab: true }));
  document.getElementById("clear-btn").addEventListener("click", () => sendControl({ clear: true }));

  const row1 = document.getElementById("pf-row-1");
  const row2 = document.getElementById("pf-row-2");
  for (let n = 1; n <= 24; n++) {
    const btn = document.createElement("button");
    btn.className = "key";
    btn.textContent = `PF${n}`;
    btn.addEventListener("click", () => sendControl({ pf: n }));
    (n <= 12 ? row1 : row2).appendChild(btn);
  }
}

function main() {
  setupTerminal();
  setupKeybar();
  renderScreen(latestState);
  renderStatus(latestState);

  socket = io();
  socket.on("state", onState);
}

main();
