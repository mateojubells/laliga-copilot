// Punto de entrada de los contratos: tipos generados + utilidades de tipo escritas a mano.
import type { Graphic } from "./contracts";

export * from "./contracts";

/** Unión discriminada por `kind` de todos los payloads. */
export type Payload = Graphic["payload"];
export type GraphicKind = Payload["kind"];
export type PayloadOf<K extends GraphicKind> = Extract<Payload, { kind: K }>;

export const GRAPHIC_KINDS = [
  "player_card",
  "team_card",
  "pass_network",
  "connection",
  "shot_map",
  "heat_map",
  "comparison",
  "standings",
  "h2h",
  "situation",
  "timeline",
  "scorebug",
] as const satisfies readonly GraphicKind[];
