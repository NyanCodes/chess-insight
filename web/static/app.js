import { api, postJson } from "./api.js";
import { START, createBoard } from "./board.js";
import { barPercent, drawGraph, formatEval, score } from "./graph.js";

const $ = (id) => document.getElementById(id);
const SAMPLE = `[Event "Scholar's Mate"]\n\n1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0\n\n[Event "Fool's Mate"]\n\n1. f3 e5 2. g4 Qh4# 0-1\n`;

const state = { jobId: null, data: null, gameIndex: 0, ply: 0, after: false, locale: "en" };
let board;

// Build DOM with textContent only: PGN headers, SAN and opening names are untrusted input.
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  const { class: cls, text, ...rest } = props;
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  for (const [k, v] of Object.entries(rest)) node.setAttribute(k, v);
  node.append(...children);
  return node;
}
const game = () => state.data?.games?.[state.gameIndex];
const rowAt = (ply) => game()?.moves.find((m) => m.ply === ply);
const label = (m) => `${m.number}${m.side === "white" ? "." : "..."} ${m.san}`;
const chip = (cls) => el("span", { class: `chip ${cls}`, text: cls === "none" ? "ok" : cls });

function setStatus(text, error = false) {
  $("status").textContent = text;
  $("status").className = error ? "error" : "";
}

// ---------- rendering ----------
function renderMoves() {
  const list = $("moves");
  list.replaceChildren();
  const g = game();
  if (!g) return;
  for (const m of g.moves) {
    const loss = m.cp_loss == null ? "" : String(m.cp_loss);
    const li = el("li", { "data-ply": m.ply },
      el("span", { class: "num", text: `${m.number}${m.side === "white" ? "." : "…"}` }),
      el("span", { class: "san", text: m.san }), chip(m.classification), el("span", { class: "loss", text: loss }));
    li.addEventListener("click", () => select(m.ply));
    list.append(li);
  }
}

function renderBoard() {
  const g = game(), m = rowAt(state.ply);
  if (!m) {
    board.show(g ? g.start_fen : START);
    $("caption").textContent = g ? "Start position" : "";
    setBar(g?.moves[0]?.eval_before);
    return;
  }
  if (state.after) {
    board.show(m.fen_after, [["warning", m.played_squares]]);
    $("caption").textContent = `After ${label(m)}`;
    setBar(m.eval_after);
  } else {
    const same = m.uci === m.best_move_uci;
    board.show(m.fen_before, same ? [["success", m.best_squares]] : [["success", m.best_squares], ["warning", m.played_squares]]);
    $("caption").textContent = `Before ${label(m)} — green: engine's best (${m.best_move_san})` + (same ? "" : ", orange: played");
    setBar(m.eval_before);
  }
}

function setBar(ev) {
  const s = score(ev);
  $("evalfill").style.height = `${barPercent(s)}%`;
  $("evaltext").textContent = formatEval(ev);
}

function renderInspector() {
  const m = rowAt(state.ply);
  const title = $("ititle"), sentences = $("sentences"), engine = $("engine");
  sentences.replaceChildren(); engine.replaceChildren();
  if (!m) {
    title.textContent = "Inspector";
    sentences.append(el("li", { class: "empty", text: "Select a move to see why." }));
    $("raw").textContent = "";
    return;
  }
  title.replaceChildren(el("span", { text: `${label(m)} ` }), chip(m.classification));
  if (!m.annotations.length) sentences.append(el("li", { class: "empty", text: "No annotations for this move." }));
  for (const a of m.annotations) sentences.append(el("li", {}, el("span", { class: "key", text: a.key }), el("span", { text: a.text })));
  $("raw").textContent = JSON.stringify(m.annotations.map(({ key, params }) => ({ key, params })), null, 2);
  const mover = (ev) => (ev ? `mover: ${ev.mate_mover != null ? "M" + ev.mate_mover : ev.cp_mover ?? "—"}` : "");
  const rows = [
    ["Played", `${m.san} (${m.uci})`], ["Best", `${m.best_move_san} (${m.best_move_uci})`],
    ["Classification", m.classification], ["cp_loss", m.cp_loss == null ? "null (mate score involved)" : `${m.cp_loss}`],
    ["Eval before", `${formatEval(m.eval_before)} White · ${mover(m.eval_before)}`],
    ["Eval after", m.eval_after ? `${formatEval(m.eval_after)} White · ${mover(m.eval_after)}` : `game over (${m.terminal_result ?? "?"})`],
    ["Best line", m.best_pv_san || "—"], ["FEN before", m.fen_before ?? "—"],
  ];
  for (const [k, v] of rows) engine.append(el("dt", { text: k }), el("dd", { text: v }));
}

function renderGraph() {
  const g = game();
  drawGraph($("graph"), g ? g.moves : [], state.ply, (index) => select(index === 0 ? 0 : g.moves[index - 1].ply));
}

function renderSelection() {
  for (const li of $("moves").children) li.classList.toggle("sel", Number(li.dataset.ply) === state.ply);
  $("moves").querySelector(".sel")?.scrollIntoView({ block: "nearest" });
  $("prev").disabled = $("first").disabled = state.ply <= 0;
  $("next").disabled = $("last").disabled = !game() || state.ply >= (game().moves.at(-1)?.ply ?? 0);
  renderBoard(); renderInspector(); renderGraph();
  if (state.jobId) history.replaceState(null, "", `#job=${state.jobId}&game=${state.gameIndex}&ply=${state.ply}`);
}

function select(ply) { state.ply = ply; renderSelection(); }
function step(delta) {
  const plies = [0, ...(game()?.moves.map((m) => m.ply) ?? [])];
  const at = plies.indexOf(state.ply);
  select(plies[Math.max(0, Math.min(plies.length - 1, (at < 0 ? 0 : at) + delta))]);
}

function renderGames() {
  const picker = $("game");
  picker.replaceChildren();
  state.data.games.forEach((g, i) => picker.append(el("option", { value: i, text: `Game ${g.game}: ${g.headers.Event ?? "(untitled)"} — ${g.result}` })));
  picker.hidden = state.data.games.length < 2;
  picker.value = String(state.gameIndex);
}

function renderPosition(position) {
  $("moves").replaceChildren(el("li", { class: "empty" }, el("span", { class: "muted", text: "FEN analysis: engine candidates" })));
  const top = position.lines[0];
  const squares = top ? { from: top.best_move_uci.slice(0, 2), to: top.best_move_uci.slice(2, 4) } : null;
  board.show(position.fen, [["success", squares]]);
  $("caption").textContent = `${position.turn} to move`;
  $("sentences").replaceChildren(el("li", { class: "empty", text: "Explanations are per move, so they need a PGN." }));
  $("raw").textContent = JSON.stringify(position.lines, null, 2);
  $("engine").replaceChildren();
  position.lines.forEach((l, i) => $("engine").append(el("dt", { text: `Line ${i + 1}` }), el("dd", { text: `${l.best_move_san}  ${formatEval(l.evaluation)}  ${l.pv_san}` })));
  setBar(top?.evaluation);
  $("graph").replaceChildren();
  $("report").textContent = "The narration is written for PGN games.";
  $("count").textContent = "";
}

// ---------- data ----------
async function loadAnnotations() {
  const body = await api(`api/annotations/${state.jobId}?locale=${encodeURIComponent(state.locale)}`);
  if (body.source === "fen") { state.data = null; renderPosition(body.position); return; }
  state.data = body;
  state.gameIndex = Math.min(state.gameIndex, body.games.length - 1);
  renderGames(); renderMoves();
  state.ply = rowAt(state.ply) ? state.ply : 0;
  renderSelection();
}

async function loadReport() {
  if (!state.data) return;
  const q = new URLSearchParams({ locale: state.locale, player: $("player").value });
  try {
    const body = await api(`api/report/${state.jobId}?${q}`);
    $("report").textContent = body.text;
    $("count").textContent = `${body.text.length} / 3500 characters`;
  } catch (e) { $("report").textContent = e.message; $("count").textContent = ""; }
}

async function showJob() {
  await loadAnnotations();
  await loadReport();
}

function watch(jobId) {
  return new Promise((resolve) => {
    const done = (snap) => { $("progress").hidden = true; resolve(snap); };
    const update = (snap) => {
      const { ply, total } = snap.progress;
      $("progress").hidden = false; $("progress").max = Math.max(1, total); $("progress").value = ply;
      setStatus(snap.state === "queued" ? "Waiting for the engine…" : `Analysing ply ${ply} / ${total}`);
    };
    const poll = async () => {
      const snap = await api(`api/jobs/${jobId}`);
      update(snap);
      return ["done", "failed", "busy"].includes(snap.state) ? done(snap) : setTimeout(poll, 400);
    };
    if (!("EventSource" in window)) return poll();
    const source = new EventSource(`api/jobs/${jobId}/events`);
    source.addEventListener("progress", (e) => update(JSON.parse(e.data)));
    source.addEventListener("end", (e) => { source.close(); done(JSON.parse(e.data)); });
    source.onerror = () => { source.close(); poll(); };       // fall back to polling
  });
}

async function analyze(event) {
  event.preventDefault();
  const text = $("pgn").value.trim();
  if (!text) return setStatus("Paste a PGN or FEN first.", true);
  const looksLikeFen = /^[rnbqkpRNBQKP1-8/]+ [wb] /.test(text) && !text.includes("\n");
  $("analyze").disabled = true; setStatus("Starting…");
  try {
    const request = { seconds: Number($("seconds").value), ...(looksLikeFen ? { fen: text } : { pgn_text: text }) };
    const { job_id } = await postJson("api/analyze", request);
    state.jobId = job_id; state.gameIndex = 0; state.ply = 0;
    const final = await watch(job_id);
    if (final.state === "done") { setStatus("Done."); await showJob(); }
    else setStatus(final.state === "busy" ? "The engine is busy with another analysis. Try again in a moment." : `Failed: ${final.error?.message ?? "unknown error"}`, true);
  } catch (e) {
    setStatus(e.message, true);
  } finally { $("analyze").disabled = false; }
}

async function init() {
  board = createBoard($("board"));
  $("input").addEventListener("submit", analyze);
  $("sample").addEventListener("click", () => { $("pgn").value = SAMPLE; });
  $("file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 512 * 1024) return setStatus("That file is larger than 512 KB.", true);
    $("pgn").value = await file.text(); setStatus(`Loaded ${file.name}`);
  });
  $("first").addEventListener("click", () => select(0));
  $("prev").addEventListener("click", () => step(-1));
  $("next").addEventListener("click", () => step(1));
  $("last").addEventListener("click", () => game() && select(game().moves.at(-1).ply));
  $("flip").addEventListener("click", () => board.flip());
  $("which").addEventListener("click", () => {
    state.after = !state.after;
    $("which").textContent = `Position: ${state.after ? "after" : "before"}`;
    renderSelection();
  });
  $("game").addEventListener("change", (e) => { state.gameIndex = Number(e.target.value); state.ply = 0; renderMoves(); renderSelection(); });
  $("locale").addEventListener("change", async (e) => { state.locale = e.target.value; if (state.jobId) await showJob(); });
  $("player").addEventListener("change", loadReport);
  document.addEventListener("keydown", (e) => {
    if (/^(TEXTAREA|SELECT|INPUT)$/.test(document.activeElement?.tagName)) return;
    if (e.key === "ArrowLeft") step(-1); else if (e.key === "ArrowRight") step(1);
    else if (e.key === "Home") select(0); else if (e.key === "End" && game()) select(game().moves.at(-1).ply);
  });

  try {
    const { locales } = await api("api/locales");
    for (const l of locales) $("locale").append(el("option", { value: l.code, text: l.name === l.code ? l.code : `${l.name} (${l.code})` }));
    state.locale = locales.some((l) => l.code === "en") ? "en" : locales[0].code;
    $("locale").value = state.locale;
  } catch (e) { setStatus(e.message, true); }

  const hash = new URLSearchParams(location.hash.slice(1));      // #job=<id>&game=0&ply=6
  if (hash.get("job")) {
    state.jobId = hash.get("job"); state.gameIndex = Number(hash.get("game") || 0); state.ply = Number(hash.get("ply") || 0);
    try { await showJob(); } catch (e) { setStatus(e.message, true); }
  } else {
    renderSelection();
  }
}

init();
