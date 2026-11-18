import { FormDots, Panel, StatTile } from "../design";
import "./TeamCard.css";
import { Reveal } from "./shared";
import type { GraphicProps } from "./types";

/** Ficha de equipo (tercio inferior): posición ("LÍDER" si es 1.º) y puntos, forma reciente y 4 StatTile sin percentiles. */
export function TeamCard({ payload, demoData }: GraphicProps<"team_card">) {
  const { team, scope, position, points, form, stats } = payload;
  const tiles = stats.slice(0, 4);
  return (
    <Panel
      kicker="Ficha de equipo"
      title={team.name}
      team={team}
      scopeLabel={scope.label}
      demoData={demoData}
      format="lower"
      from="bottom"
      className="team-card"
    >
      <div className="tc__row">
        {position != null && (
          <Reveal className="tc__fig" data-testid="tc-pos">
            {position === 1 ? <b className="display tc__leader">LÍDER</b> : <b className="display num">{position}<sup>º</sup></b>}
            {/* con "LÍDER" la etiqueta sobra, pero se conserva su hueco para que las líneas base coincidan */}
            <span className={position === 1 ? "tc__ghost" : undefined} aria-hidden={position === 1 ? true : undefined}>Posición</span>
          </Reveal>
        )}
        {points != null && (
          <Reveal className="tc__fig tc__fig--pts" data-testid="tc-pts">
            <b className="display num">{points}</b>
            <span>Puntos</span>
          </Reveal>
        )}
        {form && form.length > 0 && (
          <Reveal className="tc__form">
            <FormDots form={form} size={36} />
            <span>Últimos {form.length}</span>
          </Reveal>
        )}
        <div className="tc__grid" style={{ gridTemplateColumns: `repeat(${Math.max(1, tiles.length)}, 1fr)` }}>
          {tiles.map((s) => (
            <Reveal key={s.key}>
              <StatTile label={s.label} value={s.display} bar={false} highlight={s.highlight} />
            </Reveal>
          ))}
        </div>
      </div>
    </Panel>
  );
}
