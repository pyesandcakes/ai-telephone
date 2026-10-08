"use strict";
const $ = (id) => document.getElementById(id);
const control = document.body.dataset.page === "control";
const combined = location.pathname === "/combined";
if (location.pathname === "/image") document.body.classList.add("image-only");
if (combined) {
  document.body.classList.add("combined");
  $("back-controls").hidden = false;
  document.title = "AI Telephone · image + interpretation";
}
let token = sessionStorage.getItem("telephone-token") || "";
if (control && location.hash.startsWith("#token=")) {
  token = new URLSearchParams(location.hash.slice(1)).get("token");
  sessionStorage.setItem("telephone-token", token);
  history.replaceState(null, "", "/");
}
let selectedRun = "", offset = 0, active = false, frameKey = "", historyKey = "";
async function api(path, data) {
  const res = await fetch(path, {method: data === undefined ? "GET" : "POST",
    headers: control ? {Authorization: `Bearer ${token}`, "Content-Type": "application/json"} : {},
    body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(8000)});
  const result = await res.json();
  if (!res.ok) throw new Error(result.error || `HTTP ${res.status}`);
  return result;
}
function notice(message) { $("notice").textContent = message || ""; $("notice").hidden = !message; }
function fitWallText() {
  if (control || location.pathname === '/image') return;
  const text = $('wall-text');
  text.style.fontSize = '';
  let size = parseFloat(getComputedStyle(text).fontSize);
  while (text.scrollHeight > text.clientHeight + 1 && size > 16) {
    size -= 1;
    text.style.fontSize = `${size}px`;
  }
}
window.addEventListener('resize', fitWallText);
async function loadFrame(frame) {
  if (!frame) return;
  const key = `${frame.run}:${frame.iteration}`;
  if (frameKey === key) return;
  const image = new Image();
  image.src = frame.image;
  await image.decode();
  if (control) {
    $("preview-image").src = image.src; $("preview-image").hidden = false;
    $("preview-text").textContent = frame.caption;
  } else if (combined) {
    $("wall-image").src = image.src; $("wall-image").hidden = false;
    $("wall-text").textContent = frame.caption;
  } else if (location.pathname === "/image") {
    $("wall-image").src = image.src; $("wall-image").hidden = false; $("wall-text").hidden = true;
  } else {
    $("wall-text").textContent = frame.caption;
  }
  if (!control) $("iteration").textContent = `Iteration ${String(frame.iteration).padStart(3, "0")}`;
  fitWallText();
  frameKey = key;
}
async function showHistory() {
  if (!selectedRun) { $("history").replaceChildren(); return; }
  const run = selectedRun, page = offset;
  const data = await api(`/api/history?run=${run}&offset=${page}`);
  if (run !== selectedRun || page !== offset) return;
  $("history").replaceChildren();
  for (const item of data.items) {
    const row = document.createElement("article"); row.className = "history-row";
    const image = document.createElement("img"); image.src = `/images/${run}/${item.image}`;
    image.alt = `Iteration ${item.iteration}`; image.loading = "lazy";
    const text = document.createElement("div"), label = document.createElement("small"), caption = document.createElement("p");
    label.textContent = `#${item.iteration} · seed ${item.seed} · ${item.seconds}s`;
    caption.textContent = item.caption;
    const details = document.createElement("details"), summary = document.createElement("summary"), input = document.createElement("p");
    summary.textContent = "Image input (host only)"; input.textContent = item.input;
    details.append(summary, input); text.append(label, caption, details);
    const button = document.createElement("button"); button.className = "secondary";
    button.textContent = "Replay"; button.disabled = active;
    button.onclick = async () => { try { await api("/api/replay", {run, iteration: item.iteration}); notice(""); } catch(e) { notice(e.message); } };
    row.append(image, text, button); $("history").append(row);
  }
  $("newer").disabled = offset === 0; $("older").disabled = offset + 50 >= data.total;
  $("page-info").textContent = `${data.total ? offset + 1 : 0}–${Math.min(offset + 50, data.total)} of ${data.total}`;
}
async function poll() {
  try {
    const state = await api(control ? "/api/admin" : "/api/state");
    await loadFrame(state.frame);
    if (control) {
      active = state.active;
      $("status").textContent = `${state.demo ? "DEMO · " : ""}${state.phase}`;
      $("start").disabled = active; $("stop").disabled = !active || state.phase === "stopping";
      $("logs").textContent = state.events.map(e => `${e.time.slice(11,19)}  ${e.event}${e.iteration ? ` · #${e.iteration}` : ""}${e.detail ? ` · ${e.detail}` : ""}`).join("\n") || "No events yet.";
      if (state.error) notice(state.error);
      const runsKey = state.runs.map(r => `${r.id}:${r.status}`).join();
      if ($("runs").dataset.key !== runsKey) {
        $("runs").replaceChildren(...state.runs.map(r => {
          const option = document.createElement("option"); option.value = r.id;
          option.textContent = `${new Date(r.created).toLocaleString()} · ${r.demo ? "demo · " : ""}${r.status}`;
          return option;
        }));
        if (!selectedRun && state.runs.length) selectedRun = state.runs[0].id;
        $("runs").value = selectedRun; $("runs").dataset.key = runsKey;
      }
      const key = `${selectedRun}:${offset}:${frameKey}:${active}`;
      if (key !== historyKey) { await showHistory(); historyKey = key; }
    } else {
      $("connection").textContent = `${state.demo ? "DEMO · " : ""}${state.phase}`;
    }
  } catch(e) {
    if (control) { $("status").textContent = "Disconnected"; notice(e.message); }
    else $("connection").textContent = "Disconnected · retrying…";
  } finally { setTimeout(poll, 1000); }
}
if (control) {
  $("start-form").onsubmit = async (event) => {
    event.preventDefault(); $("start").disabled = true;
    const data = {prompt: $("prompt").value, vision_model: $("vision_model").value};
    for (const key of ["interval", "limit", "seed", "steps"]) data[key] = Number($(key).value);
    try { const result = await api("/api/start", data); selectedRun = result.run; offset = 0; historyKey = ""; notice(""); }
    catch(e) { notice(e.message); $("start").disabled = false; }
  };
  $("stop").onclick = async () => { try { await api("/api/stop", {}); } catch(e) { notice(e.message); } };
  $("runs").onchange = () => { selectedRun = $("runs").value; offset = 0; historyKey = ""; };
  $("newer").onclick = () => { offset = Math.max(0, offset - 50); historyKey = ""; };
  $("older").onclick = () => { offset += 50; historyKey = ""; };
} else {
  $("fullscreen").onclick = async () => {
    try { await document.documentElement.requestFullscreen(); document.body.classList.add("clean"); }
    catch { $("connection").textContent = "Use your browser’s fullscreen shortcut"; }
    try { if ("wakeLock" in navigator) await navigator.wakeLock.request("screen"); } catch {}
  };
}
poll();

