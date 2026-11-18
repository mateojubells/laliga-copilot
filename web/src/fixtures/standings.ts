import type { Standings, StandingsRowG, TeamRef } from "../contracts";
import { SEASON_SCOPE } from "./helpers";
import { LEAGUE_TEAMS } from "./teams";

type F = "W" | "D" | "L";
const forms = (s: string) => s.split("") as F[];

// [equipo, G, E, P, GF, GC, forma] — 30 jornadas. Cifras INVENTADAS (no son las de la clasificación real).
const TABLE: [keyof typeof LEAGUE_TEAMS, number, number, number, number, number, string][] = [
  ["barcelona", 22, 4, 4, 82, 33, "WWWDW"],
  ["real_madrid", 20, 6, 4, 62, 29, "WDWWL"],
  ["atletico", 19, 7, 4, 55, 24, "WWDWW"],
  ["athletic", 17, 8, 5, 54, 29, "DWWDW"],
  ["villarreal", 16, 7, 7, 63, 46, "LWWLW"],
  ["mallorca", 15, 6, 9, 40, 36, "WLDWL"],
  ["osasuna", 13, 9, 8, 36, 38, "DDWLD"],
  ["betis", 13, 9, 8, 44, 40, "WDLWD"],
  ["celta", 13, 7, 10, 49, 45, "LWLWW"],
  ["rayo", 12, 9, 9, 36, 38, "DLWDL"],
  ["real_sociedad", 12, 6, 12, 31, 33, "LWDLW"],
  ["girona", 12, 5, 13, 44, 48, "WLLWL"],
  ["sevilla", 10, 10, 10, 37, 42, "DDLDW"],
  ["getafe", 10, 9, 11, 29, 31, "LDDWL"],
  ["alaves", 10, 8, 12, 34, 41, "LLWDD"],
  ["valencia", 9, 11, 10, 33, 42, "DLDDW"],
  ["espanyol", 9, 8, 13, 30, 42, "LDLWL"],
  ["las_palmas", 8, 6, 16, 32, 49, "LLWLD"],
  ["leganes", 6, 11, 13, 28, 46, "DLLDL"],
  ["valladolid", 3, 5, 22, 22, 70, "LLLDL"],
];

function zoneOf(pos: number): StandingsRowG["zone"] {
  if (pos <= 4) return "champions";
  if (pos <= 6) return "europa";
  if (pos === 7) return "conference";
  if (pos >= 18) return "relegation";
  return null;
}

/** Los puntos y la diferencia de goles se calculan a partir de G/E/P y GF/GC, así la tabla es coherente. */
const rows: StandingsRowG[] = TABLE.map(([id, w, d, l, gf, ga, f]) => {
  const t: TeamRef = LEAGUE_TEAMS[id];
  return {
    pos: 0,
    team: t,
    played: w + d + l,
    won: w,
    drawn: d,
    lost: l,
    gf,
    ga,
    gd: gf - ga,
    points: w * 3 + d,
    form: forms(f),
    zone: null,
    highlight: id === "barcelona" || id === "valladolid",
  };
})
  .sort((a, b) => b.points - a.points || b.gd - a.gd || b.gf - a.gf)
  .map((r, i) => ({ ...r, pos: i + 1, zone: zoneOf(i + 1) }));

export const standingsFull: Standings = { kind: "standings", scope: SEASON_SCOPE, rows, window: "full", live: false };
export const standingsTop: Standings = { ...standingsFull, rows: rows.slice(0, 8), window: "top" };
