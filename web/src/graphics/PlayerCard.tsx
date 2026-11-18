import { NumberPill, Panel, StatTile } from "../design";
import type { PlayerRef, Stat } from "../contracts";
import { es } from "../fixtures/helpers";
import "./PlayerCard.css";
import type { GraphicProps } from "./types";

export const POSITION_ES: Record<PlayerRef["position"], string> = {
  GK: "Portero",
  RB: "Lateral derecho",
  CB: "Central",
  LB: "Lateral izquierdo",
  DM: "Pivote",
  CM: "Centrocampista",
  AM: "Mediapunta",
  RW: "Extremo derecho",
  LW: "Extremo izquierdo",
  ST: "Delantero centro",
};

/** Hasta `n` estadísticas conservando el orden, y sin dejar fuera nunca la destacada. */
export function pickStats(stats: readonly Stat[], n: number): Stat[] {
  const first = stats.slice(0, n);
  const hl = stats.find((s) => s.highlight);
  if (hl && !first.includes(hl)) first[n - 1] = hl;
  return first;
}

/** "1 gol · 2 tiros · 3 regates" → [{n:"1", t:"gol"}, …] para pintar la cifra grande y la palabra pequeña. */
function matchParts(line: string): { n: string | null; t: string }[] {
  return line.split("·").map((p) => {
    const m = p.trim().match(/^(\d+(?:[.,]\d+)?)\s+(.*)$/);
    return m ? { n: m[1]!, t: m[2]! } : { n: null, t: p.trim() };
  });
}

/** Ficha de jugador (medio panel): nombre, dorsal, dato de hoy en banda propia y 4 StatTile con "TOP x %". */
export function PlayerCard({ payload, demoData }: GraphicProps<"player_card">) {
  const { player, stats, headline, match_line, scope } = payload;
  return (
    <Panel
      title={player.known_as}
      headline={headline}
      team={player.team}
      scopeLabel={scope.label}
      demoData={demoData}
      format="half"
      from="left"
      className="player-card pc"
    >
      <div className="pc__meta caps">
        {player.number != null && <NumberPill number={player.number} className="pc__num" />}
        <span>{POSITION_ES[player.position]}</span>
        <span className="pc__dot">·</span>
        <span>{player.team.name}</span>
      </div>

      {match_line && (
        <div className="pc__today" data-testid="pc-today">
          <b className="pc__today-l caps">En este partido</b>
          <span className="pc__today-v">
            {matchParts(match_line).map((p, i) => (
              <span key={i} className="pc__part">
                {p.n != null && <b className="pc__n display num">{p.n}</b>}
                {p.t}
              </span>
            ))}
          </span>
        </div>
      )}

      <div className="pc__grid">
        {pickStats(stats, 4).map((s) => (
          <StatTile
            key={s.key}
            label={s.label}
            value={s.display}
            percentile={s.percentile}
            highlight={s.highlight}
            sub={s.per90 != null ? `${es(s.per90, 2)} por 90'` : null}
          />
        ))}
      </div>
    </Panel>
  );
}
