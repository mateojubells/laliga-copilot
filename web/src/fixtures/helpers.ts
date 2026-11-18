import type { PlayerRef, Scope, Stat, TeamRef } from "../contracts";

type Position = PlayerRef["position"];
type Line = PlayerRef["line"];

/** PRNG determinista (mulberry32) para que los fixtures sean estables entre ejecuciones y tests. */
export function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function team(id: string, name: string, short: string, primary: string, secondary: string, text = "#ffffff"): TeamRef {
  return { id, name, short, colors: { primary, secondary, text }, crest: `/api/img/crest/${id}.svg` };
}

const LINE_OF: Record<Position, Line> = {
  GK: "GK", RB: "DEF", CB: "DEF", LB: "DEF", DM: "MID", CM: "MID", AM: "MID", RW: "FWD", LW: "FWD", ST: "FWD",
};

export function player(
  slug: string,
  name: string,
  known_as: string,
  number: number | null,
  position: Position,
  t: TeamRef,
): PlayerRef {
  return {
    id: `${t.id}/${slug}`,
    name,
    known_as,
    number,
    position,
    line: LINE_OF[position],
    team: t,
    avatar: `/api/img/player/${t.id}/${slug}.svg`,
  };
}

/** Número en español: coma decimal. */
export function es(n: number, digits = 0): string {
  const [int, dec] = n.toFixed(digits).split(".");
  const miles = int!.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return dec ? `${miles},${dec}` : miles;
}

export function stat(
  key: string,
  label: string,
  value: number,
  opts: { digits?: number; display?: string; per90?: number; percentile?: number; highlight?: boolean } = {},
): Stat {
  const { digits = 0, display, per90, percentile, highlight = false } = opts;
  return {
    key,
    label,
    value,
    display: display ?? es(value, digits),
    per90: per90 ?? null,
    percentile: percentile ?? null,
    highlight,
  };
}

export const SEASON_SCOPE: Scope = {
  kind: "season",
  label: "LaLiga 2024-25 · hasta la J30",
  season: "2024-25",
  until_round: 30,
  match: null,
};
