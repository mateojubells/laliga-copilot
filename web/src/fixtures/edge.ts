import type {
  Comparison, ConnectionG, GraphicKind, H2HG, HeatMap, NetNode, PassNetworkG, PayloadOf, PlayerCard, Scorebug, ShotMap, Situation,
  Standings, TeamCard, Timeline, TimelineItem,
} from "../contracts";
import { player, SEASON_SCOPE, stat } from "./helpers";
import { standingsFull } from "./standings";
import {
  INIGO_V, JUGADOR_SIN_DORSAL, MADRID_CLARO, SOCIEDAD_FUTBOL, TER_STEGEN_V, VALLADOLID, JUMA, MARCOS_ANDRE,
} from "./teams";

/**
 * CASOS LÍMITE (galería `?case=edge`): una segunda variante por grafismo con los datos incómodos de una retransmisión real.
 * Protagonista del Valladolid (violeta y blanco), un club de primario casi blanco (Real Madrid) y otro casi negro (colores de
 * prueba), nombres largos ("Íñigo Martínez Berridi", "Marc-André ter Stegen", "Real Sociedad de Fútbol"), cifras de 4 dígitos, ceros y
 * listas vacías. Todo es DEMO: nada de esto son datos reales.
 */

// ---------------------------------------------------------------- player_card
export const playerCardEdge: PlayerCard = {
  kind: "player_card",
  player: INIGO_V,
  scope: SEASON_SCOPE,
  headline: "El central con más pases largos completados de la categoría en lo que va de temporada",
  stats: [
    stat("minutes", "Minutos jugados", 2847, { percentile: 96, highlight: true }),
    stat("goals", "Goles", 0, { percentile: 0 }),
    stat("passes", "Pases completados", 1234, { percentile: 81 }),
    stat("tackles", "Entradas", 0),
  ],
  percentile_context: { group: "Centrales de LaLiga", n: 40, min_minutes: 900 },
  form: [],
  match_line: "0 goles · 0 tiros · 1.204 pases",
};

// ---------------------------------------------------------------- team_card
export const teamCardEdge: TeamCard = {
  kind: "team_card",
  team: SOCIEDAD_FUTBOL,
  scope: SEASON_SCOPE,
  position: 20,
  points: 0,
  form: [],
  stats: [
    stat("gf", "Goles a favor", 0),
    stat("ga", "Goles en contra", 1234, { display: "1.234" }),
    stat("passes", "Pases completados", 12345, { display: "12.345" }),
    stat("possession", "Posesión", 0, { display: "0 %" }),
  ],
};

// ---------------------------------------------------------------- pass_network
const NAMES: [string, string, number, string][] = [
  ["Marc-André ter Stegen", "Marc-André ter Stegen", 1, "GK"],
  ["Íñigo Martínez Berridi", "Íñigo Martínez Berridi", 4, "CB"],
  ["Jon Ander Garitano", "Garitano", 2, "RB"],
  ["Pau Torres Lluch", "Pau Torres", 3, "LB"],
  ["Real Sociedad de Fútbol", "Aritz", 5, "CB"],
  ["Mikel Merino Zazón", "Merino", 6, "DM"],
  ["Martín Zubimendi Ibáñez", "Zubimendi", 8, "CM"],
  ["Takefusa Kubo", "Kubo", 14, "RW"],
  ["Brais Méndez Portela", "Brais Méndez", 23, "AM"],
  ["Mikel Oyarzabal Ugarte", "Oyarzabal", 10, "LW"],
  ["Alexander Sørloth", "Sørloth", 9, "ST"],
];
const POS: [number, number][] = [[7, 34], [24, 27], [30, 10], [31, 58], [24, 41], [41, 34], [53, 24], [76, 9], [54, 44], [74, 59], [84, 34]];
export const passNetworkEdge: PassNetworkG = {
  kind: "pass_network",
  team: SOCIEDAD_FUTBOL,
  scope: SEASON_SCOPE,
  nodes: NAMES.map(([name, known, n, pos], i): NetNode => ({
    player: player(`edge-${i}`, name, known, n, pos as "GK", SOCIEDAD_FUTBOL),
    x: POS[i]![0], y: POS[i]![1], passes: i === 0 ? 0 : 20 + i * 5, touches: 30 + i * 6, highlight: false,
  })),
  edges: [], // ningún par llega al mínimo de pases
  min_passes: 10,
  headline: "Ninguna pareja supera los 10 pases entre los dos",
};

// ---------------------------------------------------------------- connection
export const connectionEdge: ConnectionG = {
  kind: "connection",
  a: TER_STEGEN_V,
  b: INIGO_V,
  scope: SEASON_SCOPE,
  a_to_b: 0,
  b_to_a: 0,
  key_passes: 0,
  assists: 0,
  rank_for_a: 0,
  headline: "Sin un solo pase entre los dos en lo que va de temporada",
  arrows: [],
  a_pos: [8, 34],
  b_pos: [26, 26],
};

// ---------------------------------------------------------------- shot_map
export const shotMapEdge: ShotMap = {
  kind: "shot_map",
  subject: JUGADOR_SIN_DORSAL,
  subject_type: "player",
  scope: SEASON_SCOPE,
  shots: [],
  totals: [stat("shots", "Tiros", 0), stat("goals", "Goles", 0, { highlight: true }), stat("xg", "xG", 0, { digits: 1 })],
};

// ---------------------------------------------------------------- heat_map
export const heatMapEdge: HeatMap = {
  kind: "heat_map",
  subject: MADRID_CLARO,
  subject_type: "team",
  scope: SEASON_SCOPE,
  metric: "touches",
  cols: 21,
  rows: 14,
  grid: Array<number>(21 * 14).fill(0), // sin toques: cada celda a 0 (no hay máximo que normalizar)
  total: 0,
  zones: [],
  headline: "Sin toques registrados en este partido",
};

// ---------------------------------------------------------------- comparison
const cmp = (key: string, label: string, a: number, b: number, da = String(a), db = String(b)) =>
  ({
    key, label, a: stat(key, label, a, { display: da }), b: stat(key, label, b, { display: db }),
    better: a === b ? "tie" : a > b ? "a" : "b", higher_is_better: true,
  }) as Comparison["rows"][number];
export const comparisonEdge: Comparison = {
  kind: "comparison",
  subject_type: "player",
  a: INIGO_V,
  b: TER_STEGEN_V,
  scope: SEASON_SCOPE,
  rows: [
    cmp("minutes", "Minutos jugados", 2847, 1234, "2.847", "1.234"),
    cmp("goals", "Goles", 0, 0),
    cmp("long", "Pases largos completados por partido", 0, 1002, "0", "1.002"),
    cmp("saves", "Paradas", 1234, 0, "1.234", "0"),
  ],
  headline: "Dos jugadores del mismo club, uno sin un solo gol y otro sin una sola parada",
};

// ---------------------------------------------------------------- standings
const R = standingsFull.rows;
export const standingsEdge: Standings = {
  ...standingsFull,
  rows: R.map((r, i) => {
    if (i === 0) return { ...r, team: SOCIEDAD_FUTBOL, played: 1234, points: 1002, gd: 1234, gf: 1234, highlight: true };
    if (i === 1) return { ...r, team: MADRID_CLARO, highlight: true };
    if (r.team.id === "valladolid") return { ...r, played: 0, won: 0, drawn: 0, lost: 0, gf: 0, ga: 0, gd: -1002, points: 0, form: [] };
    return r;
  }),
};

// ---------------------------------------------------------------- h2h
export const h2hEdge: H2HG = {
  kind: "h2h",
  a: VALLADOLID,
  b: SOCIEDAD_FUTBOL,
  played: 0,
  a_wins: 0,
  draws: 0,
  b_wins: 0,
  a_goals: 0,
  b_goals: 0,
  last: [],
};

// ---------------------------------------------------------------- situation
export const situationEdge: Situation = {
  kind: "situation",
  event_type: "falta",
  title: "Falta",
  subject: INIGO_V,
  subject_type: "player",
  other: TER_STEGEN_V,
  role_label: "Falta peligrosa cometida",
  scope: SEASON_SCOPE,
  stats: [
    stat("fouls", "Faltas cometidas", 1234, { highlight: true, display: "1.234" }),
    stat("cards", "Tarjetas amarillas", 0),
  ],
  this_match: [],
  shots: [],
};

// ---------------------------------------------------------------- timeline
// Todo "auto": en antena no sale ningún evento (línea de tiempo vacía); con `?editorial=1` se ven los nombres largos.
const ev = (id: string, minute: number, type: string, label: string, team: TimelineItem["team"], players: TimelineItem["players"], major = false): TimelineItem =>
  ({ id, minute, period: minute <= 45 ? 1 : 2, t_audio: minute * 60, type, label, team, players, status: "auto", major });
export const timelineEdge: Timeline = {
  kind: "timeline",
  home: VALLADOLID,
  away: MADRID_CLARO,
  minute: 94,
  items: [
    ev("x1", 12, "gol", "Gol · Íñigo Martínez Berridi", VALLADOLID, [INIGO_V], true),
    ev("x2", 13, "amarilla", "Amarilla · Marc-André ter Stegen", VALLADOLID, [TER_STEGEN_V]),
    ev("x3", 88, "gol", "Gol · Abde Ezzalzouli", MADRID_CLARO, [JUGADOR_SIN_DORSAL], true),
    ev("x4", 90, "cambio", "Cambio · entra Marcos André por Juma Bah", VALLADOLID, [MARCOS_ANDRE, JUMA]),
  ],
};

// ---------------------------------------------------------------- scorebug
export const scorebugEdge: Scorebug = {
  kind: "scorebug",
  home: MADRID_CLARO,
  away: VALLADOLID,
  home_goals: 10,
  away_goals: 0,
  minute: 90,
  added: 12,
  period: 2,
};

export const EDGE_FIXTURES: { [K in GraphicKind]: PayloadOf<K> } = {
  player_card: playerCardEdge,
  team_card: teamCardEdge,
  pass_network: passNetworkEdge,
  connection: connectionEdge,
  shot_map: shotMapEdge,
  heat_map: heatMapEdge,
  comparison: comparisonEdge,
  standings: standingsEdge,
  h2h: h2hEdge,
  situation: situationEdge,
  timeline: timelineEdge,
  scorebug: scorebugEdge,
};
