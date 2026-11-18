/* AUTO-GENERADO por `npm run gen:contracts` desde copilot/graphics/payloads.py. NO EDITAR A MANO. */

export interface CopilotContracts {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Arrow".
 */
export interface Arrow {
  x: number;
  y: number;
  end_x: number;
  end_y: number;
  kind?: "pass" | "key_pass" | "assist" | "cross" | "carry";
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Comparison".
 */
export interface Comparison {
  kind: "comparison";
  subject_type: "player" | "team";
  a: PlayerRef | TeamRef;
  b: PlayerRef | TeamRef;
  scope: Scope;
  rows: ComparisonRow[];
  headline?: string | null;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "PlayerRef".
 */
export interface PlayerRef {
  id: string;
  name: string;
  known_as: string;
  number?: number | null;
  position: "GK" | "RB" | "CB" | "LB" | "DM" | "CM" | "AM" | "RW" | "LW" | "ST";
  line: "GK" | "DEF" | "MID" | "FWD";
  team: TeamRef;
  avatar: string;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "TeamRef".
 */
export interface TeamRef {
  id: string;
  name: string;
  short: string;
  colors: {
    [k: string]: string;
  };
  crest: string;
}
/**
 * A qué periodo corresponden los datos (siempre anterior al partido en curso, salvo kind=match).
 *
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Scope".
 */
export interface Scope {
  kind: "season" | "match" | "last_n";
  label: string;
  season: string;
  until_round?: number | null;
  match?: string | null;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "ComparisonRow".
 */
export interface ComparisonRow {
  key: string;
  label: string;
  a: Stat;
  b: Stat;
  better: "a" | "b" | "tie";
  higher_is_better?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Stat".
 */
export interface Stat {
  key: string;
  label: string;
  value: number;
  display: string;
  per90?: number | null;
  percentile?: number | null;
  highlight?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "ConnectionG".
 */
export interface ConnectionG {
  kind: "connection";
  a: PlayerRef;
  b: PlayerRef;
  scope: Scope;
  a_to_b: number;
  b_to_a: number;
  key_passes: number;
  assists: number;
  rank_for_a: number;
  headline: string;
  arrows: Arrow[];
  /**
   * @minItems 2
   * @maxItems 2
   */
  a_pos: [number, number];
  /**
   * @minItems 2
   * @maxItems 2
   */
  b_pos: [number, number];
}
/**
 * GraphicCommand tal como llega al navegador (payload tipado).
 *
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Graphic".
 */
export interface Graphic {
  id: string;
  kind: string;
  priority?: number;
  ttl_ms?: number;
  pinned?: boolean;
  state?: "proposed" | "on_air" | "retracted";
  reason?: {
    [k: string]: unknown;
  };
  payload:
    | PlayerCard
    | TeamCard
    | PassNetworkG
    | ConnectionG
    | ShotMap
    | HeatMap
    | Comparison
    | Standings
    | H2HG
    | Situation
    | Timeline
    | Scorebug;
  demo_data?: boolean;
  ts?: {
    [k: string]: number;
  };
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "PlayerCard".
 */
export interface PlayerCard {
  kind: "player_card";
  player: PlayerRef;
  scope: Scope;
  headline?: string | null;
  stats: Stat[];
  percentile_context?: PercentileContext | null;
  form?: Stat[];
  match_line?: string | null;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "PercentileContext".
 */
export interface PercentileContext {
  group: string;
  n: number;
  min_minutes: number;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "TeamCard".
 */
export interface TeamCard {
  kind: "team_card";
  team: TeamRef;
  scope: Scope;
  position?: number | null;
  points?: number | null;
  form?: ("W" | "D" | "L")[];
  stats: Stat[];
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "PassNetworkG".
 */
export interface PassNetworkG {
  kind: "pass_network";
  team: TeamRef;
  scope: Scope;
  nodes: NetNode[];
  edges: NetEdge[];
  min_passes: number;
  headline?: string | null;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "NetNode".
 */
export interface NetNode {
  player: PlayerRef;
  x: number;
  y: number;
  passes: number;
  touches: number;
  highlight?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "NetEdge".
 */
export interface NetEdge {
  a: string;
  b: string;
  count: number;
  highlight?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "ShotMap".
 */
export interface ShotMap {
  kind: "shot_map";
  subject: PlayerRef | TeamRef;
  subject_type: "player" | "team";
  scope: Scope;
  shots: Shot[];
  totals: Stat[];
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Shot".
 */
export interface Shot {
  x: number;
  y: number;
  xg: number;
  outcome: "goal" | "saved" | "off" | "blocked" | "post";
  minute: number;
  player: string;
  player_name: string;
  body?: string | null;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "HeatMap".
 */
export interface HeatMap {
  kind: "heat_map";
  subject: PlayerRef | TeamRef;
  subject_type: "player" | "team";
  scope: Scope;
  metric?: "touches" | "recoveries" | "passes_received" | "shots";
  cols: number;
  rows: number;
  grid: number[];
  total: number;
  zones?: Stat[];
  headline?: string | null;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Standings".
 */
export interface Standings {
  kind: "standings";
  scope: Scope;
  rows: StandingsRowG[];
  window?: "full" | "top" | "around";
  live?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "StandingsRowG".
 */
export interface StandingsRowG {
  pos: number;
  team: TeamRef;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  gd: number;
  points: number;
  form?: ("W" | "D" | "L")[];
  zone?: ("champions" | "europa" | "conference" | "relegation") | null;
  highlight?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "H2HG".
 */
export interface H2HG {
  kind: "h2h";
  a: TeamRef;
  b: TeamRef;
  played: number;
  a_wins: number;
  draws: number;
  b_wins: number;
  a_goals: number;
  b_goals: number;
  last: H2HMatch[];
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "H2HMatch".
 */
export interface H2HMatch {
  season: string;
  date: string;
  home: TeamRef;
  away: TeamRef;
  home_goals: number;
  away_goals: number;
}
/**
 * Situación de juego (penalti, falta, regate, córner…) con el histórico del protagonista.
 *
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Situation".
 */
export interface Situation {
  kind: "situation";
  event_type: string;
  title: string;
  subject?: PlayerRef | TeamRef | null;
  subject_type?: ("player" | "team") | null;
  other?: PlayerRef | null;
  role_label?: string | null;
  scope: Scope;
  stats: Stat[];
  this_match?: Stat[];
  shots?: Shot[];
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Timeline".
 */
export interface Timeline {
  kind: "timeline";
  home: TeamRef;
  away: TeamRef;
  items: TimelineItem[];
  minute?: number | null;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "TimelineItem".
 */
export interface TimelineItem {
  id: string;
  minute?: number | null;
  period?: number | null;
  t_audio: number;
  type: string;
  label: string;
  team?: TeamRef | null;
  players?: PlayerRef[];
  status?: "auto" | "approved" | "edited" | "discarded";
  major?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "Scorebug".
 */
export interface Scorebug {
  kind: "scorebug";
  home: TeamRef;
  away: TeamRef;
  home_goals: number;
  away_goals: number;
  minute?: number | null;
  period?: number | null;
  added?: number | null;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "MatchState".
 */
export interface MatchState {
  match: string;
  home: TeamRef;
  away: TeamRef;
  home_goals?: number;
  away_goals?: number;
  period?: 0 | 1 | 2 | 3;
  minute?: number | null;
  on_pitch?: {
    [k: string]: string[];
  };
  possession_subject?: string | null;
  clock_running?: boolean;
  clock_base_s?: number;
  clock_at_ms?: number | null;
  added?: number | null;
}
/**
 * Servidor → navegador. type decide qué campo viene relleno.
 *
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "ServerMsg".
 */
export interface ServerMsg {
  type:
    | "hello"
    | "transcript"
    | "graphic"
    | "graphic_hide"
    | "program"
    | "program_clear"
    | "event"
    | "state"
    | "status"
    | "latency";
  server_now: number;
  graphic?: Graphic | null;
  graphic_id?: string | null;
  transcript?: {
    [k: string]: unknown;
  } | null;
  event?: {
    [k: string]: unknown;
  } | null;
  state?: MatchState | null;
  data?: {
    [k: string]: unknown;
  } | null;
}
/**
 * Navegador → servidor.
 *
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "OperatorAction".
 */
export interface OperatorAction {
  type:
    | "approve"
    | "pin"
    | "unpin"
    | "discard"
    | "take"
    | "clear_program"
    | "edit_event"
    | "discard_event"
    | "add_event"
    | "request"
    | "set_auto"
    | "replay_control"
    | "say"
    | "painted"
    | "ping"
    | "clock"
    | "voice"
    | "panic"
    | "set_score";
  graphic_id?: string | null;
  event_id?: string | null;
  event?: {
    [k: string]: unknown;
  } | null;
  request?: {
    [k: string]: unknown;
  } | null;
  text?: string | null;
  value?: boolean | number | string | null;
  t_paint?: number | null;
  client_now?: number | null;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "SeasonInfoOut".
 */
export interface SeasonInfoOut {
  season: string;
  teams: number;
  players: number;
  has_results: boolean;
  has_stats: boolean;
  current?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "MatchListItem".
 */
export interface MatchListItem {
  id: string;
  season: string;
  round: number;
  date: string;
  home: TeamRef;
  away: TeamRef;
  home_goals?: number | null;
  away_goals?: number | null;
  has_lineup?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "TeamLineup".
 */
export interface TeamLineup {
  starting: string[];
  bench: string[];
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "LineupProposal".
 */
export interface LineupProposal {
  match: string;
  source: "saved" | "proposed";
  teams: {
    [k: string]: TeamLineup;
  };
  squads: {
    [k: string]: PlayerRef[];
  };
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "SessionConfig".
 */
export interface SessionConfig {
  season: string;
  match: string;
  lineups: {
    [k: string]: TeamLineup;
  };
  voice?: "mic" | "replay" | "none";
  auto_program?: boolean;
}
/**
 * This interface was referenced by `CopilotContracts`'s JSON-Schema
 * via the `definition` "SessionInfo".
 */
export interface SessionInfo {
  config?: SessionConfig | null;
  started_at?: string | null;
  resumed?: boolean;
  home?: TeamRef | null;
  away?: TeamRef | null;
  events?: number;
  score?: {
    [k: string]: number;
  } | null;
}
