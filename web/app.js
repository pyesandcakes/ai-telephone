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
let modeInitialized = false;
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
  if (combined && !$("original-prompt-panel").hidden) {
    document.body.style.setProperty("--prompt-space", `${$("original-prompt-panel").getBoundingClientRect().bottom + 20}px`);
  }
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
  if (!frame) {
    frameKey = "";
    if (control) {
      $("preview-image").hidden = true; $("preview-image").removeAttribute("src");
      $("preview-text").textContent = "Waiting for the first translation.";
    } else {
      $("wall-image").hidden = true; $("wall-image").removeAttribute("src");
      $("wall-text").textContent = "";
      $("wall-text").hidden = location.pathname === "/image";
      $("iteration").textContent = ""; $("provenance").hidden = true;
    }
    return;
  }
  if (!control) {
    $("provenance").hidden = !frame.demo && !frame.recorded;
    $("provenance").textContent = frame.recorded ? (frame.demo ? "Simulated saved chain · playback" : "Recorded real-model chain · playback") : "Simulated demo · authored artwork / scripted interpretation";
  }
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
    label.textContent = `${item.demo ? "SIMULATED · " : ""}#${item.iteration} · seed ${item.seed} · ${item.seconds}s`;
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
    const state = await api(control ? "/api/admin" : combined ? "/api/combined-state" : "/api/state");
    if (combined) {
      $("original-prompt-panel").hidden = !state.original_prompt;
      $("original-prompt").textContent = state.original_prompt || "";
      document.body.classList.toggle("has-original-prompt", !!state.original_prompt);
    }
    await loadFrame(state.frame);
    if (combined) fitWallText();
    if (control) {
      active = state.active;
      if (!modeInitialized) {
        $("mode").value = state.default_mode || "live-demo";
        $("vision_model").value = state.default_vision_model || "qwen2.5vl:3b";
        updateMode(); modeInitialized = true;
      }
      $("mode-label").hidden = state.demo || state.recorded;
      $("mode-hint").hidden = state.demo || state.recorded;
      $("mode").disabled = active;
      $("demo-note").hidden = !state.demo && !state.recorded;
      if (state.recorded) {
        $("demo-note").textContent = "RECORDED REAL-MODEL CHAIN · Original images and vision interpretations. Playback performs no new inference.";
        $("prompt").value = state.recorded_prompt;
        $("prompt").readOnly = true;
        $("start").textContent = "Play recorded chain";
      }
      if (state.demo && !$("prompt").dataset.demo) {
        $("prompt").value = "A luminous red ring floating above a dark blue pool at night.";
        $("prompt").readOnly = true;
        $("prompt").dataset.demo = "true";
        $("limit").value = "18"; $("limit").max = "18";
        $("start").textContent = "Play demo sequence";
      }
      $("status").textContent = `${state.demo ? "SIMULATED DEMO · " : state.recorded ? "RECORDED CHAIN · " : state.playback ? "PLAYBACK · " : ""}${state.phase}`;
      $("replay-run").disabled = active || !selectedRun;
      $("reset").disabled = active || (!state.frame && state.phase === "idle");
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
      const progress = state.progress || {completed: 0, iteration: 0, limit: 0};
      $("generation-progress").hidden = !state.active;
      if (state.active) {
        const stage = {"starting": "Starting models", "checking models": "Checking models", "downloading vision model": "Downloading selected vision model (first use)", "generating image": "Generating image", "interpreting image": "Interpreting image", "holding": "Waiting for next iteration", "playing saved run": "Playing saved run", "stopping": state.playback ? "Stopping playback" : "Stopping after current model call"}[state.phase] || state.phase;
        $("progress-label").textContent = `${stage} · iteration ${progress.iteration || 1} · ${progress.completed}${progress.limit ? ` / ${progress.limit}` : ""} ${state.playback ? "shown" : "completed"}`;
        if (progress.limit) { $("progress-bar").max = progress.limit; $("progress-bar").value = progress.completed; }
        else $("progress-bar").removeAttribute("value");
      }
      $("connection").textContent = `${state.demo ? "SIMULATED DEMO · " : state.recorded ? "RECORDED CHAIN · " : state.playback ? "PLAYBACK · " : ""}${state.phase}`;
    }
  } catch(e) {
    if (control) { $("status").textContent = "Disconnected"; notice(e.message); }
    else { $("connection").textContent = "Disconnected · retrying…"; $("generation-progress").hidden = true; }
  } finally { setTimeout(poll, 1000); }
}
function updateMode() {
  const testing = $("mode").value === "live-testing";
  $("limit").value = testing ? "0" : "18";
  $("limit").readOnly = testing;
  $("start").textContent = testing ? "Start continuous testing" : "Start live demo";
  $("mode-hint").textContent = testing ? "Your prompt starts a live feedback chain that keeps generating until you press Stop. Each interpretation becomes the next image prompt." : "Your prompt starts a live feedback chain. It stops at the iteration limit; you can also press Stop at any time.";
}
if (control) {
  $("mode").onchange = updateMode;
  $("start-form").onsubmit = async (event) => {
    event.preventDefault(); $("start").disabled = true;
    const data = {prompt: $("prompt").value, vision_model: $("vision_model").value};
    if (!$("mode-label").hidden) data.mode = $("mode").value;
    for (const key of ["interval", "limit", "seed", "steps"]) data[key] = Number($(key).value);
    try { const result = await api("/api/start", data); selectedRun = result.run; offset = 0; historyKey = ""; notice(""); }
    catch(e) { notice(e.message); $("start").disabled = false; }
  };
  $("replay-reading").onchange = () => { $("replay-interval").disabled = $("replay-reading").checked; };
  $("replay-run").onclick = async () => {
    $("replay-run").disabled = true;
    try {
      await api("/api/replay-run", {run: selectedRun, interval: $("replay-reading").checked ? null : Number($("replay-interval").value), repeat: $("replay-repeat").checked});
      notice("");
    } catch(e) { notice(e.message); }
  };
  $("reset").onclick = async () => {
    $("reset").disabled = true;
    try { await api("/api/reset", {}); await loadFrame(null); notice(""); }
    catch(e) { notice(e.message); }
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

