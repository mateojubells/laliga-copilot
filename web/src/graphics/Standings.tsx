import type { CSSProperties } from "react";
import { FormDots, Panel, TeamCrest, inkOn, useImageMode } from "../design";
import type { StandingsRowG } from "../contracts";
import "./Standings.css";
import type { GraphicProps } from "./types";

const ZONE_LABEL: Record<NonNullable<StandingsRowG["zone"]>, string> = {
  champions: "Champions League",
  europa: "Europa League",
  conference: "Conference League",
  relegation: "Descenso",
};

const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "0");

function Row({ r, full, crest }: { r: StandingsRowG; full: boolean; crest: boolean }) {
  return (
    <div
      role="row"
      className={`st__row${r.highlight ? " st__row--hl" : ""}`}
      data-zone={r.zone ?? undefined}
      data-testid="standings-row"
      style={r.highlight ? ({ "--row": r.team.colors.primary ?? "#4a515e", "--row-ink": r.team.colors.text ?? inkOn(r.team.colors.primary ?? "#4a515e") } as CSSProperties) : undefined}
    >
      <span className={`st__zone${r.zone ? ` st__zone--${r.zone}` : ""}`} title={r.zone ? ZONE_LABEL[r.zone] : undefined} />
      <span className="st__pos display num">{r.pos}</span>
      {crest && <TeamCrest team={r.team} size={30} />}
      <span className="st__name">{r.team.name}</span>
      <span className="st__n num">{r.played}</span>
      {full && (
        <>
          <span className="st__n st__n--dim num">{r.won}</span>
          <span className="st__n st__n--dim num">{r.drawn}</span>
          <span className="st__n st__n--dim num">{r.lost}</span>
        </>
      )}
      <span className="st__n st__gd num">{signed(r.gd)}</span>
      <span className="st__n st__pts display num">{r.points}</span>
      {!full && (
        <span className="st__form">
          <FormDots form={(r.form ?? []).slice(-5)} size={14} square />
        </span>
      )}
    </div>
  );
}

function Head({ full, crest }: { full: boolean; crest: boolean }) {
  return (
    <div className="st__row st__row--head caps" role="row">
      <span className="st__zone" />
      <span className="st__pos">Pos</span>
      {crest && <span />}
      <span className="st__name">Equipo</span>
      <span className="st__n">PJ</span>
      {full && (
        <>
          <span className="st__n st__n--dim">G</span>
          <span className="st__n st__n--dim">E</span>
          <span className="st__n st__n--dim">P</span>
        </>
      )}
      <span className="st__n st__gd">DG</span>
      <span className="st__n st__pts">Pts</span>
      {!full && <span className="st__form">Forma</span>}
    </div>
  );
}

/**
 * Clasificación. Dos formatos de antena:
 *  - completa (pantalla completa, solo repetición o descanso): 20 filas en dos columnas de 10 (PJ · G/E/P · DG · PTS), sin forma.
 *  - ventana (medio panel, la que se usa en partido): unas 8 filas altas con PJ · DG · PTS y la forma en cuadrados.
 */
export function Standings({ payload, demoData }: GraphicProps<"standings">) {
  const { rows, scope, live, window: win } = payload;
  const full = win === "full" || rows.length > 12;
  const crest = useImageMode() === "remote"; // los escudos generados son placas con siglas ilegibles: sin ellos no se pinta nada
  const zonesPresent = (Object.keys(ZONE_LABEL) as (keyof typeof ZONE_LABEL)[]).filter((z) => rows.some((r) => r.zone === z));
  const half = Math.ceil(rows.length / 2);
  const cols = full ? [rows.slice(0, half), rows.slice(half)] : [rows];
  return (
    <Panel
      kicker={live ? "Clasificación · en directo" : "Clasificación"}
      title={scope.until_round ? `LaLiga · Jornada ${scope.until_round}` : "LaLiga"}
      scopeLabel={scope.label}
      demoData={demoData}
      format={full ? "full" : "half"}
      from="left"
      className={`standings${full ? " standings--full" : ""}`}
      headRight={live ? <span className="st__live caps">En juego</span> : undefined}
    >
      <div className="st__cols" style={{ gridTemplateColumns: `repeat(${cols.length}, minmax(0, 1fr))` }}>
        {cols.map((c, i) => (
          <div key={i} className={`st__table${full ? " st__table--full" : ""}${crest ? "" : " st__table--nocrest"}`} role="table" aria-label="Clasificación">
            <Head full={full} crest={crest} />
            {c.map((r) => (
              <Row key={r.team.id} r={r} full={full} crest={crest} />
            ))}
          </div>
        ))}
      </div>
      {zonesPresent.length > 0 && (
        <div className="st__legend">
          {zonesPresent.map((z) => (
            <span key={z}>
              <i className={`st__swatch st__zone--${z}`} />
              {ZONE_LABEL[z]}
            </span>
          ))}
        </div>
      )}
    </Panel>
  );
}
