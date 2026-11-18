import type { CSSProperties } from "react";
import type { GraphicKind } from "../contracts";
import { Comparison } from "./Comparison";
import { Connection } from "./Connection";
import { H2H } from "./H2H";
import { HeatMap } from "./HeatMap";
import { PassNetwork } from "./PassNetwork";
import { PlayerCard } from "./PlayerCard";
import { Scorebug } from "./Scorebug";
import { ShotMap } from "./ShotMap";
import { Situation } from "./Situation";
import { Standings } from "./Standings";
import { TeamCard } from "./TeamCard";
import { Timeline } from "./Timeline";
import type { GraphicComponent } from "./types";

/**
 * Registro central kind → componente. Para añadir un grafismo: crear el componente (GraphicProps<"kind">) y
 * registrarlo aquí. El resto (galería, /program, operador) lo recoge solo.
 */
export const GRAPHICS: { [K in GraphicKind]: GraphicComponent<K> } = {
  player_card: PlayerCard,
  team_card: TeamCard,
  pass_network: PassNetwork,
  connection: Connection,
  shot_map: ShotMap,
  heat_map: HeatMap,
  comparison: Comparison,
  standings: Standings,
  h2h: H2H,
  situation: Situation,
  timeline: Timeline,
  scorebug: Scorebug,
};

/** Estado de implementación (la galería lo etiqueta). */
export const STATUS: Record<GraphicKind, "done" | "draft" | "pending"> = {
  player_card: "done",
  standings: "done",
  pass_network: "done",
  connection: "done",
  shot_map: "done",
  heat_map: "done",
  team_card: "done",
  comparison: "done",
  h2h: "done",
  situation: "done",
  timeline: "done",
  scorebug: "done",
};

/**
 * Formato de panel de cada grafismo (tres, y no siete):
 *  - lower: tercio inferior, 1792 × (≤ 320), anclado abajo. Para jugar: situation, h2h (variante "live"), timeline, team_card.
 *  - half:  medio panel, 1240 × (≈ 640-720). player_card, heat_map, connection, shot_map, comparison, y la ventana de standings.
 *  - full:  pantalla completa 1792 × 816 bajo el marcador. SOLO para repetición o descanso: pass_network y standings completa.
 *  - scorebug: marcador de esquina (700 × 88 + banda de demostración).
 * h2h tiene además la variante "full" (medio panel con últimos enfrentamientos) para previa y descanso.
 */
export const FORMAT: Record<GraphicKind, "lower" | "half" | "full" | "scorebug"> = {
  player_card: "half",
  team_card: "lower",
  standings: "full", // la ventana (window ≠ "full", ≤ 12 filas) se pinta en medio panel, mismo anclaje
  pass_network: "full",
  connection: "half",
  shot_map: "half",
  heat_map: "half",
  comparison: "half",
  h2h: "lower",
  situation: "lower",
  timeline: "lower",
  scorebug: "scorebug",
};

/** Grafismos de pantalla completa: solo se usan en repetición o descanso, nunca durante la jugada. */
export const REPLAY_OR_BREAK_ONLY: readonly GraphicKind[] = ["pass_network", "standings"];

/**
 * Posición en el lienzo de 1920×1080 (dentro de la zona segura de 64 px). La franja superior izquierda (64-200 px) es
 * del marcador (top 64, alto 88 + banda de demostración 28 = hasta y 180): nada empieza por encima de top 200.
 */
export const PLACEMENT: Record<GraphicKind, CSSProperties> = {
  player_card: { left: 64, bottom: 64 },
  team_card: { left: 64, bottom: 64 },
  standings: { left: 64, top: 200 },
  pass_network: { left: 64, top: 200 },
  connection: { left: 64, bottom: 64 },
  shot_map: { left: 64, bottom: 64 },
  heat_map: { left: 64, bottom: 64 },
  comparison: { right: 64, bottom: 64 },
  h2h: { left: 64, bottom: 64 },
  situation: { left: 64, bottom: 64 },
  timeline: { left: 64, bottom: 64 },
  scorebug: { left: 64, top: 64 },
};
