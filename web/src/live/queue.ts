import type { Graphic } from "../contracts";
import type { QueueItem } from "./types";

/** Las propuestas no fijadas se atenúan a los 60 s y se retiran de la cola a los 3 min. */
export const STALE_MS = 60_000;
export const EXPIRE_MS = 180_000;
export const MAX_QUEUE = 100;

export function ageMs(item: QueueItem, now: number): number {
  return Math.max(0, now - item.receivedAt);
}

export function isStale(item: QueueItem, now: number, onAir = false): boolean {
  return !item.graphic.pinned && !onAir && ageMs(item, now) >= STALE_MS;
}

export function isExpired(item: QueueItem, now: number, onAir = false): boolean {
  return !item.graphic.pinned && !onAir && ageMs(item, now) >= EXPIRE_MS;
}

export function ageLabel(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 5) return "ahora";
  if (s < 60) return `hace ${s} s`;
  return `hace ${Math.floor(s / 60)} min`;
}

export const KIND_LABEL: Record<string, string> = {
  player_card: "Ficha de jugador",
  team_card: "Ficha de equipo",
  pass_network: "Red de pases",
  connection: "Conexión",
  shot_map: "Mapa de tiros",
  heat_map: "Mapa de calor",
  comparison: "Comparativa",
  standings: "Clasificación",
  h2h: "Cara a cara",
  situation: "Situación",
  timeline: "Cronología",
  scorebug: "Marcador",
};

type Ref = { known_as?: string; short?: string; name?: string };
const nm = (r?: Ref | null) => r?.known_as ?? r?.short ?? r?.name ?? "";

/** Protagonista(s) legibles de un grafismo, para la tarjeta de la cola. */
export function protagonists(g: Graphic): string {
  const p = g.payload;
  switch (p.kind) {
    case "player_card": return nm(p.player);
    case "team_card": return nm(p.team);
    case "pass_network": return nm(p.team);
    case "connection": return `${nm(p.a)} ↔ ${nm(p.b)}`;
    case "shot_map":
    case "heat_map": return nm(p.subject);
    case "comparison": return `${nm(p.a)} vs ${nm(p.b)}`;
    case "h2h": return `${nm(p.a)} vs ${nm(p.b)}`;
    case "situation": return [p.title, nm(p.subject), p.other ? `→ ${nm(p.other)}` : ""].filter(Boolean).join(" · ");
    case "standings": return p.scope?.label ?? "";
    case "timeline": return `${nm(p.home)} – ${nm(p.away)}`;
    case "scorebug": return `${nm(p.home)} ${p.home_goals}-${p.away_goals} ${nm(p.away)}`;
  }
}

export function reasonOf(g: Graphic): { trigger: string; text: string } {
  const r = (g.reason ?? {}) as Record<string, unknown>;
  return { trigger: typeof r.trigger === "string" ? r.trigger : "", text: typeof r.text === "string" ? r.text : "" };
}
