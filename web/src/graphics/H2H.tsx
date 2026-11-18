import { motion } from "framer-motion";
import type { CSSProperties } from "react";
import type { H2HMatch, TeamRef } from "../contracts";
import { Panel, TeamCrest, growVariants, rowVariants, type FormResult } from "../design";
import "./H2H.css";
import { Reveal, fmtDate } from "./shared";
import type { GraphicProps } from "./types";

/** Gris del empate: el mismo de la "E" de las bolitas de forma. */
const NEUTRAL = "#6b7585";

/** Resultado del partido desde el punto de vista de `a`. */
export function resultFor(m: H2HMatch, a: TeamRef): FormResult {
  const aHome = m.home.id === a.id;
  const mine = aHome ? m.home_goals : m.away_goals;
  const theirs = aHome ? m.away_goals : m.home_goals;
  return mine > theirs ? "W" : mine < theirs ? "L" : "D";
}

/**
 * Cara a cara histórico: balance como barra segmentada con los colores de cada club y goles integrados en la barra.
 * Dos variantes: "live" (por defecto, tercio inferior: solo héroe y barra, para jugar) y "full" (medio panel, con los
 * últimos enfrentamientos: previa o descanso).
 */
export function H2H({ payload, demoData, variant = "live" }: GraphicProps<"h2h">) {
  const { a, b, played, a_wins, draws, b_wins, a_goals, b_goals, last } = payload;
  const full = variant === "full";
  // colores REALES de cada club (sin aclarar): la barra es un bloque; las cifras van en blanco
  const ca = a.colors.primary ?? "#445566";
  const cb = b.colors.primary && b.colors.primary !== ca ? b.colors.primary : (b.colors.secondary ?? "#7a869a");
  const segs = [
    { key: "a", n: a_wins, color: ca },
    { key: "d", n: draws, color: NEUTRAL },
    { key: "b", n: b_wins, color: cb },
  ];
  // las CIFRAS reparten el ancho como la barra pero con un mínimo de 160 px (hace falta sitio para escudo + cifra); la BARRA es
  // estrictamente proporcional: un tramo con 0 partidos no se pinta ni ocupa columna (no puede medir 160 px "por legibilidad")
  const present = segs.filter((x) => x.n > 0);
  const cols = present.length === 0 ? "1fr 1fr 1fr" : segs.map((x) => `minmax(160px, ${Math.max(x.n, 0.0001)}fr)`).join(" ");
  const barCols = present.map((x) => `${x.n}fr`).join(" ");
  const empty = present.length === 0;
  return (
    <Panel
      kicker="Cara a cara"
      title={`${a.name} · ${b.name}`}
      team={a}
      crest={false}
      scopeLabel={`${played} partidos`}
      demoData={demoData}
      format={full ? "half" : "lower"}
      from={full ? "left" : "bottom"}
      className={`h2h${full ? " h2h--full" : ""}`}
      style={{ "--ca": ca, "--cb": cb } as CSSProperties}
    >
      <div className="h2h__grid">
        <Reveal className="h2h__hero" style={{ gridTemplateColumns: cols }}>
          <div className={`h2h__fig h2h__fig--a${a_wins === 0 ? " is-zero" : ""}`}>
            <TeamCrest team={a} size={64} />
            <div className="h2h__col">
              <b className="h2h__num display num" data-testid="h2h-a">{a_wins}</b>
              <span>Victorias</span>
            </div>
          </div>
          <div className={`h2h__fig h2h__fig--d${draws === 0 ? " is-zero" : ""}`}>
            <div className="h2h__col">
              <b className="h2h__num display num" data-testid="h2h-d">{draws}</b>
              <span>Empates</span>
            </div>
          </div>
          <div className={`h2h__fig h2h__fig--b${b_wins === 0 ? " is-zero" : ""}`}>
            <div className="h2h__col">
              <b className="h2h__num display num" data-testid="h2h-b">{b_wins}</b>
              <span>Victorias</span>
            </div>
            <TeamCrest team={b} size={64} />
          </div>
        </Reveal>

        <Reveal className="h2h__g h2h__g--a">
          <b className="h2h__gn display num">{a_goals}</b>
          <span>Goles</span>
        </Reveal>
        <div
          className={`h2h__bar${empty ? " h2h__bar--empty" : ""}`}
          style={empty ? undefined : { gridTemplateColumns: barCols }}
          role="img"
          aria-label={`${a_wins} victorias de ${a.name}, ${draws} empates, ${b_wins} victorias de ${b.name}`}
          data-testid="h2h-bar"
        >
          {empty && <span className="h2h__none">Sin enfrentamientos previos</span>}
          {present.map((sg, i) => (
            <motion.i
              key={sg.key}
              data-seg={sg.key}
              data-n={sg.n}
              style={{ gridColumn: i + 1, background: sg.color, transformOrigin: "left center" }}
              variants={growVariants}
              custom={i}
            />
          ))}
        </div>
        <Reveal className="h2h__g h2h__g--b">
          <b className="h2h__gn display num">{b_goals}</b>
          <span>Goles</span>
        </Reveal>
        <span className="sr-only" data-testid="h2h-goals">{a_goals} – {b_goals}</span>
      </div>

      {full && (
        <>
          <div className="sd__label h2h__lh">Últimos enfrentamientos</div>
          <ol className="h2h__list" data-testid="h2h-last">
            {last.map((m, i) => {
              const res = resultFor(m, a);
              const homeWon = m.home_goals > m.away_goals;
              const awayWon = m.away_goals > m.home_goals;
              const winner = res === "W" ? ca : res === "L" ? cb : NEUTRAL;
              return (
                <motion.li key={m.date} className="h2h__m" variants={rowVariants} custom={i} data-testid="h2h-match">
                  <span className="h2h__date">{fmtDate(m.date)}</span>
                  <span className={`h2h__team h2h__team--home${homeWon ? " is-win" : ""}`}>{m.home.short}</span>
                  <span className="h2h__score display num">
                    {m.home_goals} – {m.away_goals}
                  </span>
                  <span className={`h2h__team h2h__team--away${awayWon ? " is-win" : ""}`}>{m.away.short}</span>
                  {/* el color es el del club que ganó (neutro si empataron): no hace falta leyenda V/E/D */}
                  <i className="h2h__chip" style={{ background: winner }} data-result={res} aria-label={res === "W" ? `Ganó ${a.short}` : res === "L" ? `Ganó ${b.short}` : "Empate"} />
                </motion.li>
              );
            })}
          </ol>
        </>
      )}
    </Panel>
  );
}
