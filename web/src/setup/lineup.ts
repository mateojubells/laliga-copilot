import type { PlayerRef, TeamLineup } from "../contracts";

export type Slot = "starting" | "bench" | "out";

export interface LineupCheck {
  ok: boolean;
  starters: number;
  keepers: number;
  errors: string[];
}

/** Reglas: exactamente 11 titulares, de ellos exactamente 1 portero (position GK). */
export function validateLineup(lu: TeamLineup, squad: PlayerRef[]): LineupCheck {
  const pos = new Map(squad.map((p) => [p.id, p.position]));
  const starters = lu.starting.length;
  const keepers = lu.starting.filter((id) => pos.get(id) === "GK").length;
  const errors: string[] = [];
  if (starters !== 11) errors.push(`Hay ${starters} titulares: deben ser 11.`);
  if (keepers !== 1) errors.push(keepers === 0 ? "Falta el portero titular." : `Hay ${keepers} porteros titulares: debe haber 1.`);
  if (lu.starting.some((id) => lu.bench.includes(id))) errors.push("Un jugador está a la vez de titular y de suplente.");
  return { ok: errors.length === 0, starters, keepers, errors };
}

export function slotOf(lu: TeamLineup, id: string): Slot {
  return lu.starting.includes(id) ? "starting" : lu.bench.includes(id) ? "bench" : "out";
}

/** Mueve un jugador a otra lista (sin duplicados). El orden de las listas es el de entrada. */
export function movePlayer(lu: TeamLineup, id: string, to: Slot): TeamLineup {
  const starting = lu.starting.filter((x) => x !== id);
  const bench = lu.bench.filter((x) => x !== id);
  if (to === "starting") starting.push(id);
  else if (to === "bench") bench.push(id);
  return { starting, bench };
}

/** Clic en el jugador: titular → banquillo, banquillo → titular, no convocado → banquillo. */
export function clickMove(lu: TeamLineup, id: string): TeamLineup {
  const s = slotOf(lu, id);
  return movePlayer(lu, id, s === "starting" ? "bench" : s === "bench" ? "starting" : "bench");
}

const LINE_ORDER = { GK: 0, DEF: 1, MID: 2, FWD: 3 } as const;
/** Porteros, defensas, medios, delanteros; dentro, por dorsal. */
export const byLine = (a: PlayerRef, b: PlayerRef) =>
  LINE_ORDER[a.line] - LINE_ORDER[b.line] || (a.number ?? 99) - (b.number ?? 99) || a.known_as.localeCompare(b.known_as);
