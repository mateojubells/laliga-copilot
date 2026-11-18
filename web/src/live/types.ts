import type { Graphic, MatchState, OperatorAction, ServerMsg } from "../contracts";

export type Role = "operator" | "program";

/** MatchEvent tal como lo manda el servidor (copilot/types.py). */
export interface MatchEvent {
  id: string;
  t_audio: number;
  minute?: number | null;
  period?: number | null;
  type: string;
  fine?: string;
  roles: Record<string, string>;
  team?: string | null;
  source?: "nlu" | "operator" | "feed";
  status: "auto" | "approved" | "edited" | "discarded";
  confidence?: number;
  text?: string;
  trace_id?: string;
}

export interface TranscriptLine {
  id: string;
  text: string;
  t0: number;
  t1: number;
  engine?: string;
}

export interface QueueItem {
  graphic: Graphic;
  /** Instante (Date.now()) en que llegó al navegador: de aquí cuelga la caducidad visual. */
  receivedAt: number;
  /** Llegó ya marcada on_air por el selector (prioridad alta / automático). */
  auto: boolean;
}

export interface ProgramEntry {
  graphic: Graphic;
  since: number;
}

export interface EngineStatus {
  asr?: string;
  data?: string;
  errors?: number;
  last_error?: string;
  replay?: { mode?: string; speed?: number; from?: number } | null;
  /** Estado del motor de voz del servidor: "off" | "starting" | "on" | "error". */
  voice?: string;
  /** Nivel (0..1) del audio que recibe el servidor por /ws/audio. */
  mic_level?: number;
  /** Páginas /program conectadas ahora mismo. */
  program_clients?: number;
  /** Hay un partido configurado en el servidor. */
  session?: boolean;
}

export interface LiveState {
  connected: boolean;
  /** Se ha conectado alguna vez (para no enseñar "sin conexión" en el arranque). */
  everConnected: boolean;
  match: MatchState | null;
  finals: TranscriptLine[];
  partial: TranscriptLine | null;
  graphics: Record<string, QueueItem>;
  /** Ids de la cola, el más nuevo primero. */
  order: string[];
  program: ProgramEntry | null;
  events: MatchEvent[];
  status: EngineStatus;
  autoProgram: boolean;
  /** Último "replay_started" del servidor; `n` crece con cada arranque para disparar efectos. */
  replayStarted: { audio_t: number; speed: number; n: number } | null;
}

export type LiveAction =
  | { type: "msg"; msg: ServerMsg; now: number }
  | { type: "conn"; connected: boolean }
  | { type: "snapshot"; data: Snapshot; now: number }
  | { type: "tick"; now: number }
  | { type: "program_expire"; id: string };

export interface Snapshot {
  state?: MatchState | null;
  events?: MatchEvent[];
  graphics?: Graphic[];
  program?: Graphic | null;
}

export type { Graphic, MatchState, OperatorAction, ServerMsg };
