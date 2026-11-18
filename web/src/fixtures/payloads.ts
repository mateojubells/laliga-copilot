import type {
  Arrow, Comparison, ConnectionG, H2HG, HeatMap, NetEdge, NetNode, PassNetworkG, PlayerCard, Scorebug, Shot, ShotMap,
  Situation, TeamCard, Timeline, TimelineItem,
} from "../contracts";
import { rng, SEASON_SCOPE, stat } from "./helpers";
import {
  BALDE, BARCELONA, CUBARSI, DE_JONG, FERMIN, HEIN, INIGO, JUMA, JURIC, KOUNDE, LAMINE, LEWANDOWSKI, MARCOS_ANDRE,
  OLMO, PEDRI, RAPHINHA, RAUL_MORO, SZCZESNY, VALLADOLID,
} from "./teams";

// Todas las cifras de este fichero son INVENTADAS (demo_data: true). Solo los nombres de equipos y jugadores son reales.

// ---------------------------------------------------------------- player_card
export const playerCard: PlayerCard = {
  kind: "player_card",
  player: LAMINE,
  scope: SEASON_SCOPE,
  headline: "El extremo con más asistencias de LaLiga",
  stats: [
    stat("assists", "Asistencias", 12, { percentile: 97, per90: 0.45, highlight: true }),
    stat("goals", "Goles", 8, { percentile: 88, per90: 0.3 }),
    stat("xg", "xG", 6.4, { digits: 1, percentile: 79, per90: 0.24 }),
    stat("key_passes", "Pases clave", 58, { percentile: 94, per90: 2.2 }),
    stat("dribbles_won", "Regates ganados", 71, { percentile: 91, per90: 2.7 }),
    stat("pass_pct", "Precisión de pase", 83, { display: "83 %", percentile: 62 }),
  ],
  percentile_context: { group: "Extremos de LaLiga", n: 34, min_minutes: 900 },
  form: [],
  match_line: "1 gol · 2 tiros · 3 regates",
};

// ---------------------------------------------------------------- team_card
export const teamCard: TeamCard = {
  kind: "team_card",
  team: BARCELONA,
  scope: SEASON_SCOPE,
  position: 1,
  points: 70,
  form: ["W", "W", "W", "D", "W"],
  stats: [
    stat("gf", "Goles a favor", 82, { percentile: 100 }),
    stat("ga", "Goles en contra", 33, { percentile: 71 }),
    stat("xg", "xG por partido", 2.31, { digits: 2, percentile: 100 }),
    stat("possession", "Posesión", 66, { display: "66 %", percentile: 95 }),
  ],
};

// ---------------------------------------------------------------- pass_network
const XI = [
  { p: SZCZESNY, x: 7, y: 34, passes: 41, touches: 52 },
  { p: KOUNDE, x: 30, y: 10, passes: 66, touches: 84 },
  { p: CUBARSI, x: 24, y: 27, passes: 78, touches: 91 },
  { p: INIGO, x: 24, y: 41, passes: 70, touches: 83 },
  { p: BALDE, x: 31, y: 58, passes: 52, touches: 69 },
  { p: DE_JONG, x: 41, y: 34, passes: 88, touches: 101 },
  { p: PEDRI, x: 53, y: 24, passes: 74, touches: 95 },
  { p: OLMO, x: 54, y: 44, passes: 49, touches: 67 },
  { p: LAMINE, x: 76, y: 9, passes: 38, touches: 62, highlight: true },
  { p: LEWANDOWSKI, x: 84, y: 34, passes: 22, touches: 45 },
  { p: RAPHINHA, x: 74, y: 59, passes: 36, touches: 58 },
];
const nodes: NetNode[] = XI.map(({ p, x, y, passes, touches, highlight }) => ({
  player: p, x, y, passes, touches, highlight: !!highlight,
}));
const E = (a: typeof SZCZESNY, b: typeof SZCZESNY, count: number, highlight = false): NetEdge => ({
  a: a.id, b: b.id, count, highlight,
});
const edges: NetEdge[] = [
  E(SZCZESNY, CUBARSI, 14), E(SZCZESNY, INIGO, 11), E(CUBARSI, INIGO, 22), E(INIGO, CUBARSI, 19),
  E(CUBARSI, DE_JONG, 24), E(INIGO, DE_JONG, 18), E(CUBARSI, KOUNDE, 17), E(KOUNDE, LAMINE, 21),
  E(LAMINE, KOUNDE, 12), E(DE_JONG, PEDRI, 26), E(PEDRI, DE_JONG, 20), E(PEDRI, LAMINE, 24, true),
  E(LAMINE, PEDRI, 13), E(OLMO, RAPHINHA, 15), E(BALDE, RAPHINHA, 16), E(INIGO, BALDE, 15),
  E(PEDRI, LEWANDOWSKI, 12), E(OLMO, LEWANDOWSKI, 10), E(DE_JONG, OLMO, 17), E(LAMINE, LEWANDOWSKI, 11),
];
export const passNetwork: PassNetworkG = {
  kind: "pass_network",
  team: BARCELONA,
  scope: SEASON_SCOPE,
  nodes,
  edges,
  min_passes: 10,
  headline: "Pedri → Lamine: 24 pases por partido",
};

// ---------------------------------------------------------------- connection
const r1 = rng(7);
const A_POS: [number, number] = [52, 24];
const B_POS: [number, number] = [76, 9];
// Muestra de pases de Pedri hacia la zona de Lamine: salen de la zona media de Pedri y llegan al carril derecho.
const connArrows: Arrow[] = Array.from({ length: 18 }, (_, i) => {
  const key = i % 6 === 2;
  const assist = i === 11;
  return {
    x: A_POS[0] + (r1() - 0.5) * 12,
    y: A_POS[1] + (r1() - 0.5) * 12,
    end_x: (key || assist ? 82 : 70) + r1() * 12,
    end_y: (key || assist ? 8 : 4) + r1() * 14,
    kind: assist ? "assist" : key ? "key_pass" : "pass",
  } satisfies Arrow;
});
export const connection: ConnectionG = {
  kind: "connection",
  a: PEDRI,
  b: LAMINE,
  scope: SEASON_SCOPE,
  a_to_b: 187,
  b_to_a: 96,
  key_passes: 21,
  assists: 6,
  rank_for_a: 1,
  headline: "Pedri, autor de 6 de las 12 asistencias de Lamine",
  arrows: connArrows,
  a_pos: A_POS,
  b_pos: B_POS,
};

// ---------------------------------------------------------------- shot_map
const r2 = rng(21);
// 8 goles + 18 tiros más (6 parados, 5 bloqueados, 6 fuera, 1 al palo); posiciones sin solaparse y xG según la distancia a portería.
const OUTCOME_ORDER: Shot["outcome"][] = [
  ...Array<Shot["outcome"]>(8).fill("goal"),
  "saved", "off", "blocked", "saved", "off", "blocked", "saved", "off", "blocked", "saved", "off", "blocked", "post",
  "saved", "off", "blocked", "saved", "off",
];
const taken: [number, number][] = [];
function shotSpot(close: boolean): [number, number] {
  let best: [number, number] = [90, 30];
  for (let t = 0; t < 60; t++) {
    const x = close ? 88.5 + r2() * 10.5 : 70 + r2() * 18;
    const y = close ? 16 + r2() * 32 : 4 + r2() * 42;
    best = [x, y];
    if (taken.every(([px, py]) => Math.hypot(px - x, py - y) > 3.6)) break;
  }
  taken.push(best);
  return best;
}
const lamineShots: Shot[] = OUTCOME_ORDER.map((outcome, i) => {
  const [x, y] = shotSpot(outcome === "goal" || i % 3 === 0);
  const d = Math.hypot(105 - x, 34 - y);
  const xg = Math.max(0.03, Math.min(0.78, 1.5 * Math.exp(-d / 9))) * (0.85 + r2() * 0.3);
  return {
    x, y, xg: Math.round(xg * 100) / 100, outcome, minute: 4 + ((i * 37) % 88), player: LAMINE.id, player_name: LAMINE.known_as,
    body: r2() < 0.7 ? "left_foot" : "right_foot",
  };
});
const xgSum = lamineShots.reduce((s, x) => s + x.xg, 0);
const onTarget = lamineShots.filter((x) => x.outcome === "goal" || x.outcome === "saved").length;
export const shotMap: ShotMap = {
  kind: "shot_map",
  subject: LAMINE,
  subject_type: "player",
  scope: SEASON_SCOPE,
  shots: lamineShots,
  totals: [
    stat("shots", "Tiros", lamineShots.length),
    stat("on_target", "A puerta", onTarget),
    stat("goals", "Goles", 8, { highlight: true }),
    stat("xg", "xG", xgSum, { digits: 1 }),
    stat("xg_per_shot", "xG/tiro", xgSum / lamineShots.length, { digits: 2 }),
  ],
};

// ---------------------------------------------------------------- heat_map
const COLS = 21;
const ROWS = 14;
function blob(cx: number, cy: number, sx: number, sy: number, amp: number) {
  return (c: number, r: number) => {
    const x = ((c + 0.5) / COLS) * 105;
    const y = ((r + 0.5) / ROWS) * 68;
    return amp * Math.exp(-((x - cx) ** 2) / (2 * sx ** 2) - ((y - cy) ** 2) / (2 * sy ** 2));
  };
}
const blobs = [blob(76, 9, 11, 7, 1), blob(58, 14, 12, 8, 0.55), blob(88, 24, 7, 8, 0.4), blob(40, 10, 10, 7, 0.25)];
const r3 = rng(3);
const rawGrid = Array.from({ length: COLS * ROWS }, (_, i) => {
  const c = i % COLS;
  const r = Math.floor(i / COLS);
  return blobs.reduce((s, f) => s + f(c, r), 0) * (0.9 + r3() * 0.2);
});
const gMax = Math.max(...rawGrid);
export const heatMap: HeatMap = {
  kind: "heat_map",
  subject: LAMINE,
  subject_type: "player",
  scope: SEASON_SCOPE,
  metric: "touches",
  cols: COLS,
  rows: ROWS,
  grid: rawGrid.map((v) => Math.round((v / gMax) * 1000) / 1000),
  total: 1842,
  zones: [
    stat("third_att", "Último tercio", 58, { display: "58 %" }),
    stat("right_wing", "Banda derecha", 64, { display: "64 %" }),
    stat("half_space", "Carril interior", 21, { display: "21 %" }),
  ],
  headline: "Casi dos de cada tres toques, por la banda derecha",
};

// ---------------------------------------------------------------- comparison
const cmp = (key: string, label: string, a: number, b: number, d = 0, hib = true) =>
  ({
    key,
    label,
    a: stat(key, label, a, { digits: d }),
    b: stat(key, label, b, { digits: d }),
    better: a === b ? "tie" : (a > b) === hib ? "a" : "b",
    higher_is_better: hib,
  }) as Comparison["rows"][number];
export const comparison: Comparison = {
  kind: "comparison",
  subject_type: "player",
  a: LAMINE,
  b: RAPHINHA,
  scope: SEASON_SCOPE,
  rows: [
    cmp("goals", "Goles", 8, 14),
    cmp("assists", "Asistencias", 12, 9),
    cmp("xg", "xG", 6.4, 10.2, 1),
    cmp("key_passes", "Pases clave", 58, 49),
    cmp("dribbles_won", "Regates ganados", 71, 38),
    cmp("shots", "Tiros", 26, 47),
  ],
  headline: "Lamine asiste más; Raphinha remata más",
};

// ---------------------------------------------------------------- standings: ver standings.ts

// ---------------------------------------------------------------- h2h
const m = (season: string, date: string, hg: number, ag: number, homeIsA: boolean): H2HG["last"][number] => ({
  season, date,
  home: homeIsA ? BARCELONA : VALLADOLID,
  away: homeIsA ? VALLADOLID : BARCELONA,
  home_goals: hg, away_goals: ag,
});
export const h2h: H2HG = {
  kind: "h2h",
  a: BARCELONA,
  b: VALLADOLID,
  played: 8,
  a_wins: 5,
  draws: 2,
  b_wins: 1,
  a_goals: 17,
  b_goals: 6,
  last: [
    m("2024-25", "2025-01-12", 3, 1, true),
    m("2024-25", "2024-09-01", 1, 2, false),
    m("2023-24", "2024-03-09", 2, 2, true),
    m("2023-24", "2023-10-21", 0, 2, false),
    m("2020-21", "2021-04-10", 1, 0, true),
  ],
};

// ---------------------------------------------------------------- situation
const penalty: Shot = {
  x: 94, y: 34, xg: 0.76, outcome: "goal", minute: 63, player: LAMINE.id, player_name: LAMINE.known_as, body: "right_foot",
};
export const situation: Situation = {
  kind: "situation",
  event_type: "penalti",
  title: "Penalti",
  subject: LAMINE,
  subject_type: "player",
  other: JUMA,
  role_label: "Penalti provocado",
  scope: SEASON_SCOPE,
  stats: [
    stat("penalties_won", "Penaltis provocados", 3, { highlight: true }),
    stat("fouls_drawn", "Faltas recibidas", 71),
    stat("penalties_scored", "Penaltis marcados", 2, { display: "2 · 2" }),
  ],
  this_match: [stat("fouls_drawn_match", "Faltas recibidas hoy", 4)],
  shots: [penalty],
};

// ---------------------------------------------------------------- timeline
// Estados del fixture: approved / edited salen en antena; "auto" (por defecto) y "discarded" solo en la vista de operador.
const t = (
  id: string, minute: number, t_audio: number, type: string, label: string,
  team: TimelineItem["team"], players: TimelineItem["players"], major = false, status: TimelineItem["status"] = "auto",
): TimelineItem => ({ id, minute, period: minute <= 45 ? 1 : 2, t_audio, type, label, team, players, status, major });
export const timeline: Timeline = {
  kind: "timeline",
  home: BARCELONA,
  away: VALLADOLID,
  minute: 67,
  items: [
    t("e1", 12, 740, "gol", "Gol · Raphinha", BARCELONA, [RAPHINHA], true, "approved"),
    t("e2", 23, 1390, "amarilla", "Amarilla · Juma Bah", VALLADOLID, [JUMA], false, "approved"),
    t("e3", 31, 1880, "gol", "Gol · Marcos André", VALLADOLID, [MARCOS_ANDRE], true, "approved"),
    t("e4", 44, 2650, "corner", "Córner · Barcelona", BARCELONA, []),
    t("e5", 52, 3170, "penalti", "Penalti · Lamine Yamal", BARCELONA, [LAMINE], true, "edited"),
    t("e6", 53, 3215, "gol", "Gol · Lewandowski (p)", BARCELONA, [LEWANDOWSKI], true, "approved"),
    t("e7", 61, 3700, "cambio", "Cambio · entra Fermín por Olmo", BARCELONA, [FERMIN, OLMO], false, "approved"),
    t("e8", 64, 3880, "regate", "Regate · Raúl Moro", VALLADOLID, [RAUL_MORO], false, "discarded"),
    t("e9", 66, 3990, "parada", "Parada · Karl Hein", VALLADOLID, [HEIN]),
    t("e10", 67, 4030, "tiro", "Tiro · Juric", VALLADOLID, [JURIC]),
    // sin confirmar: fuera de antena hasta que el servidor (o el operador) los apruebe
    t("e11", 65, 3930, "amarilla", "Amarilla · Cubarsí", BARCELONA, [CUBARSI]),
  ],
};

// ---------------------------------------------------------------- scorebug
export const scorebug: Scorebug = {
  kind: "scorebug",
  home: BARCELONA,
  away: VALLADOLID,
  home_goals: 2,
  away_goals: 1,
  minute: 67,
  period: 2,
};

