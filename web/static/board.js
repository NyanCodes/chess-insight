// cm-chessboard (MIT, vendored) with its arrows, markers and html-layer extensions. Assets are
// located relative to this module, so no absolute path or CDN is involved.
//
// How a move is drawn:
//  - The board library only ever sets positions instantly. Its own slide uses a fixed
//    ease-in-out curve that cannot be changed from outside, so the slide is done here with the
//    Web Animations API on short-lived "ghost" copies of the moving pieces, which allows a strong
//    ease-out (leaves fast, settles gently). The real pieces on the squares involved stay hidden
//    until the animation ends.
//  - What moves is read from the two positions (see describeStep), never guessed, so identical
//    knights or rooks cannot be mixed up. Castling slides king and rook, a promotion slides the
//    pawn and swaps the piece on arrival, a capture shrinks and fades the captured piece.
//  - Only a step of exactly one ply animates (the caller says so with `step`); everything else
//    snaps. One worker applies the newest request, so the board follows rapid input.
//  - The last move's squares stay tinted, the king in check glows, and a badge on the destination
//    square shows the move's verdict. These are static, so they appear even with reduced motion.
import { Chessboard, COLOR, FEN } from "./vendor/cm-chessboard/src/Chessboard.js";
import { Arrows, ARROW_TYPE } from "./vendor/cm-chessboard/src/extensions/arrows/Arrows.js";
import { Markers } from "./vendor/cm-chessboard/src/extensions/markers/Markers.js";
import { HtmlLayer } from "./vendor/cm-chessboard/src/extensions/html-layer/HtmlLayer.js";
import { DEFAULT_SPEED_MS } from "./speed.js";
import { describeStep, placement } from "./stepplan.js";

export const START = FEN.start;
const MIN_FAST_MS = 50;                       // shortest slide while input arrives faster than a slide
const EASE_OUT = "cubic-bezier(0.22, 1, 0.36, 1)";   // quint-like: most of the distance in the first third
const SVG_NS = "http://www.w3.org/2000/svg";  // an XML namespace identifier, never fetched
const MARK = {
  from: { class: "marker-lastmove-from", slice: "markerSquare" },
  to: { class: "marker-lastmove-to", slice: "markerSquare" },
  check: { class: "marker-check", slice: "markerSquare" },
};
const SQUARE = /^[a-h][1-8]$/;

export function createBoard(element, { speedMs = DEFAULT_SPEED_MS } = {}) {
  const board = new Chessboard(element, {
    position: FEN.start,
    assetsUrl: new URL("vendor/cm-chessboard/assets/", import.meta.url).href,
    style: { cssClass: "default", showCoordinates: true, animationDuration: 0 },
    extensions: [
      { class: Arrows },
      // Our own one-shape sprite (a plain square), so no extra third-party artwork is needed.
      { class: Markers, props: { autoMarkers: null, sprite: new URL("markers.svg", import.meta.url).href } },
      { class: HtmlLayer },
    ],
  });
  const cues = board.addHtmlLayer("");
  cues.className = "html-layer cues";
  const hideStyle = document.createElement("style");
  document.head.append(hideStyle);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  let speed = speedMs;            // the user's chosen slide time; 0 turns animation off
  let pending = null;             // newest request not yet applied
  let wantFlipped = false, flipped = false;
  let working = false, effects = null, shownCue = null;
  let lastRequestAt = -Infinity, requestGap = Infinity;

  const motionMs = () => (reducedMotion.matches || document.hidden ? 0 : speed);
  const updateBusy = () => {
    if (working || effects) element.dataset.animating = "true"; else delete element.dataset.animating;
  };

  // ---------- arrows (analysis) ----------
  function drawArrows(arrows, fadeMs) {
    board.removeArrows();
    for (const [type, squares] of arrows || []) {
      if (squares) board.addArrow(ARROW_TYPE[type], squares.from, squares.to);
    }
    const group = element.querySelector("g.arrows");
    if (!group) return;
    group.style.transition = "none";
    group.style.opacity = fadeMs > 0 ? "0" : "1";
    if (fadeMs > 0) {
      void group.getBoundingClientRect();                       // commit opacity 0 before fading in
      group.style.transition = `opacity ${fadeMs}ms ease-out`;
      group.style.opacity = "1";
    }
  }

  // ---------- last move, check, badge (static cues) ----------
  function squareBox(square) {                                  // column and row from the top-left
    const file = square.charCodeAt(0) - 97, rank = square.charCodeAt(1) - 49;
    return flipped ? { col: 7 - file, row: rank } : { col: file, row: 7 - rank };
  }

  function drawTint(cue) {
    board.removeMarkers();
    if (!cue) return;
    board.addMarker(MARK.from, cue.from);
    board.addMarker(MARK.to, cue.to);
  }

  function badgeNode(badge) {
    const node = document.createElement("div");
    node.className = `badge badge-${badge.kind}`;
    node.title = badge.label;
    node.setAttribute("role", "img");
    node.setAttribute("aria-label", badge.label);
    if (badge.glyph) {
      node.textContent = badge.glyph;
    } else {                                                    // open book, drawn here (no emoji, no asset)
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("viewBox", "0 0 20 20");
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", "M10 5.5C8.4 4.4 5.7 4 3 4.2v10.6c2.7-.2 5.4.2 7 1.3 1.6-1.1 4.3-1.5 7-1.3V4.2c-2.7-.2-5.4.2-7 1.3Z M10 5.5v10.6");
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", "currentColor");
      path.setAttribute("stroke-width", "1.7");
      path.setAttribute("stroke-linejoin", "round");
      svg.append(path);
      node.append(svg);
    }
    return node;
  }

  // Draw the cues that belong to the landing: the king in check and the badge.
  function drawLanding(cue, animate) {
    cues.replaceChildren();
    shownCue = cue;
    if (!cue) { board.removeMarkers(MARK.check); return; }
    board.removeMarkers(MARK.check);
    if (cue.check && SQUARE.test(cue.check)) board.addMarker(MARK.check, cue.check);
    if (!cue.badge || !SQUARE.test(cue.to)) return;
    const { col, row } = squareBox(cue.to);
    const node = badgeNode(cue.badge);
    node.style.setProperty("--col", col);
    node.style.setProperty("--row", row);
    cues.append(node);
    if (animate) {
      node.animate({ transform: ["scale(0.4)", "scale(1)"], opacity: [0, 1] },
                   { duration: 140, easing: "cubic-bezier(0.34, 1.4, 0.64, 1)", fill: "backwards" });
    }
  }

  // ---------- the slide ----------
  const hideSquares = (squares) => {
    hideStyle.textContent = squares.filter((s) => SQUARE.test(s))
      .map((s) => `#${element.id} g.pieces > g[data-square="${s}"] { visibility: hidden; }`).join("\n");
  };

  function origin(square) {
    const rect = element.querySelector(`g.board rect[data-square="${square}"]`);
    return rect ? { x: Number(rect.getAttribute("x")), y: Number(rect.getAttribute("y")) } : null;
  }

  function startEffects(description, ms) {
    const parent = element.querySelector("g.pieces-layer");
    const template = element.querySelector("g.pieces > g[data-piece]");
    if (!parent || !template) return null;
    const layer = document.createElementNS(SVG_NS, "g");
    layer.setAttribute("class", "ghosts");
    parent.append(layer);
    const anims = [];
    const ghost = (piece, square) => {
      const at = origin(square);
      if (!at) return null;
      const node = template.cloneNode(true);
      node.removeAttribute("data-square");
      node.setAttribute("data-piece", piece);
      node.setAttribute("transform", `translate(${at.x} ${at.y})`);
      const use = node.querySelector("use");
      const href = use.getAttribute("href");
      use.setAttribute("href", href.slice(0, href.indexOf("#") + 1) + piece);
      node.style.transformBox = "fill-box";
      node.style.transformOrigin = "50% 58%";
      layer.append(node);
      return { node, at };
    };
    const translate = (p) => `translate(${p.x}px, ${p.y}px)`;
    hideSquares(description.changed);

    // Drawn bottom to top: captured pieces, then restored ones, then the movers, so a capturing
    // piece always lands on top. The ease-out brings a mover home quickly, so the captured piece
    // starts to shrink almost at once and is already small when the mover covers its square.
    for (const gone of description.vanish) {                    // a capture: shrink and fade
      const g = ghost(gone.piece, gone.square);
      if (!g) continue;
      anims.push(g.node.animate({ opacity: [1, 0], transform: [`${translate(g.at)} scale(1)`, `${translate(g.at)} scale(0.45)`] },
                                { duration: ms * 0.7, delay: ms * 0.08, easing: "ease-out", fill: "forwards" }));
    }
    for (const back of description.appear) {                    // an undone capture: grow back in
      const g = ghost(back.piece, back.square);
      if (!g) continue;
      anims.push(g.node.animate({ opacity: [0, 1], transform: [`${translate(g.at)} scale(0.45)`, `${translate(g.at)} scale(1)`] },
                                { duration: ms * 0.7, delay: ms * 0.3, easing: "ease-out", fill: "both" }));
    }
    for (const slide of description.slides) {                   // the mover (and the castling rook)
      const g = ghost(slide.piece, slide.from), end = origin(slide.to);
      if (!g || !end) continue;
      anims.push(g.node.animate({ transform: [translate(g.at), translate(end)] },
                                { duration: ms, easing: EASE_OUT, fill: "forwards" }));
    }
    let cleaned = false;
    const cleanup = () => {
      if (cleaned) return;
      cleaned = true;
      layer.remove();
      hideSquares([]);
    };
    const run = {
      cancel() { anims.forEach((a) => a.cancel()); cleanup(); },
      done: Promise.allSettled(anims.map((a) => a.finished)).then(cleanup),
    };
    return run;
  }

  // Skip a running slide to its end. A newer request will draw its own cues; anything else that
  // interrupts (Flip) must still land the interrupted move's cues, so it passes `land`.
  function stopEffects({ land = false } = {}) {
    if (!effects) return;
    const e = effects;
    effects = null;
    e.cancel();
    updateBusy();
    if (land && e.landed) e.landed();
  }

  // ---------- applying a request ----------
  async function apply(request) {
    stopEffects();
    const ms = motionMs();
    board.removeArrows();                                      // they describe the old position
    const description = request.step && ms > 0 ? describeStep(request.step) : null;
    // Input arriving faster than a slide would take: shorten the slide so it can keep up.
    const effective = requestGap < ms ? Math.max(MIN_FAST_MS, Math.round(requestGap * 0.9)) : ms;
    const run = description ? startEffects(description, effective) : null;   // before the update: no flash
    if (run) { effects = run; updateBusy(); }
    cues.replaceChildren();
    drawTint(request.cue);                                     // the tint appears as the piece sets off
    if (board.getPosition() !== placement(request.fen)) await board.setPosition(request.fen, false);
    if (pending) return;                                       // a newer request already took over
    const landed = () => {
      if (pending) return;
      drawLanding(request.cue, !!run);
      if (!pending) drawArrows(request.arrows, run ? 160 : 0);
    };
    if (run) {
      run.landed = landed;
      run.done.then(() => { if (effects === run) { effects = null; updateBusy(); landed(); } });
    } else {
      landed();
    }
  }

  async function turn() {
    stopEffects({ land: true });
    flipped = wantFlipped;
    await board.setOrientation(flipped ? COLOR.black : COLOR.white, motionMs() > 0);
    if (shownCue) drawLanding(shownCue, false);                // the badge sits on a different screen square now
  }

  async function work() {
    working = true;
    updateBusy();
    try {
      while (pending || wantFlipped !== flipped) {
        if (pending) {
          const request = pending;
          pending = null;
          await apply(request);
        } else {
          await turn();
        }
      }
    } catch (error) {
      console.error("board update failed", error);
    } finally {
      working = false;
      updateBusy();
    }
  }

  return {
    // fen: the position to show. arrows: [[type, {from, to}], ...]. step: from stepBetween() when
    // the position is exactly one ply from the one shown before; omit it for anything else.
    // cue: from cueAt(), the move that was just played to reach this position (or null).
    show(fen, { arrows = [], step = null, cue = null } = {}) {
      // Only input that lands while an update is still running counts as "faster than a slide".
      const now = performance.now();
      requestGap = working || effects ? now - lastRequestAt : Infinity;
      lastRequestAt = now;
      pending = { fen, arrows, step, cue };
      stopEffects();                                           // a slide still running is skipped to its end
      if (!working) work();
    },
    flip() {
      wantFlipped = !wantFlipped;
      if (!working) work();
    },
    setSpeed(ms) { speed = Math.max(0, Number(ms) || 0); },
    get speed() { return speed; },
  };
}
