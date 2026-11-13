// Evaluation maths and the eval graph. Scores are White-relative centipawns; a forced
// mate is shown as a large fixed value because it has no centipawn equivalent.
export const MATE = 1000;
const CLAMP = 600;
const NS = "http://www.w3.org/2000/svg";   // an XML namespace identifier, not a network request

export function score(ev) {
  if (!ev) return null;
  if (ev.mate_white != null) return ev.mate_white > 0 ? MATE : -MATE;
  return ev.cp_white;
}

export function formatEval(ev) {
  if (!ev) return "—";
  if (ev.mate_white != null) return `${ev.mate_white > 0 ? "+" : "-"}M${Math.abs(ev.mate_white)}`;
  return ev.cp_white == null ? "—" : `${ev.cp_white >= 0 ? "+" : ""}${(ev.cp_white / 100).toFixed(2)}`;
}

// 0..100 share of the bar given to White (logistic, like most engines' win-chance curves).
export function barPercent(s) {
  if (s === null || s === undefined) return 50;
  return 100 / (1 + Math.exp(-s / 400));
}

// Series point i is the evaluation after ply i; point 0 is the start.
export function evalSeries(moves) {
  if (!moves.length) return [];
  const series = [score(moves[0].eval_before)];
  for (const m of moves) {
    let s = score(m.eval_after);
    if (s === null && m.terminal_result) s = m.terminal_result === "1-0" ? MATE : m.terminal_result === "0-1" ? -MATE : 0;
    series.push(s);
  }
  return series;
}

const svg = (tag, attrs) => {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
};
const COLORS = { inaccuracy: "#e0b341", mistake: "#e08a3c", blunder: "#e0524d", unclassified_mate: "#a06be0" };

export function drawGraph(root, moves, selectedPly, onSelect) {
  root.replaceChildren();
  const series = evalSeries(moves);
  if (series.length < 2) return;
  const W = 480, H = 96, x = (i) => (i / (series.length - 1)) * W;
  const y = (s) => H / 2 - (Math.max(-CLAMP, Math.min(CLAMP, s ?? 0)) / CLAMP) * (H / 2 - 4);
  root.append(svg("line", { x1: 0, x2: W, y1: H / 2, y2: H / 2, stroke: "#394050", "stroke-width": 1 }));
  const points = series.map((s, i) => `${x(i).toFixed(1)},${y(s).toFixed(1)}`);
  root.append(svg("polygon", { points: `0,${H / 2} ${points.join(" ")} ${W},${H / 2}`, fill: "#5b8def33" }));
  root.append(svg("polyline", { points: points.join(" "), fill: "none", stroke: "#8fb0ff", "stroke-width": 1.6,
                                "vector-effect": "non-scaling-stroke" }));
  moves.forEach((m, i) => {
    if (COLORS[m.classification]) root.append(svg("circle", { cx: x(i + 1), cy: y(series[i + 1]), r: 3, fill: COLORS[m.classification] }));
  });
  if (selectedPly > 0) {
    root.append(svg("line", { x1: x(selectedPly), x2: x(selectedPly), y1: 0, y2: H, stroke: "#ffffff", "stroke-opacity": .6, "stroke-width": 1 }));
  }
  root.onpointerdown = (event) => {
    const box = root.getBoundingClientRect();
    const index = Math.round(((event.clientX - box.left) / box.width) * (series.length - 1));
    onSelect(Math.max(0, Math.min(moves.length, index)));
  };
}
