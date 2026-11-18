import { motion } from "framer-motion";
import type { CSSProperties } from "react";
import type { ComparisonRow, PlayerRef, TeamRef } from "../contracts";
import { Panel, TeamCrest, growVariants, pairAccents, rowVariants } from "../design";
import "./Comparison.css";
import { POSITION_ES } from "./PlayerCard";
import type { GraphicProps } from "./types";

type Subject = PlayerRef | TeamRef;
const isPlayer = (s: Subject, t: "player" | "team"): s is PlayerRef => t === "player" && "known_as" in s;
const teamOf = (s: Subject, t: "player" | "team"): TeamRef => (isPlayer(s, t) ? s.team : (s as TeamRef));
const nameOf = (s: Subject, t: "player" | "team") => (isPlayer(s, t) ? s.known_as : (s as TeamRef).name);

function Contender({ s, type, color, side, sameClub }: { s: Subject; type: "player" | "team"; color: string; side: "a" | "b"; sameClub: boolean }) {
  // sin foto no hay avatar: el nombre a 56 px en el color del jugador se sostiene solo
  return (
    <div className={`cm__who cm__who--${side}`} style={{ "--c": color } as CSSProperties}>
      {!isPlayer(s, type) && <TeamCrest team={s as TeamRef} size={64} />}
      <div className="cm__names">
        <div className="cm__name display caps" style={{ fontSize: nameOf(s, type).length <= 16 ? undefined : Math.max(34, Math.floor((56 * 16) / nameOf(s, type).length)) }}>{nameOf(s, type)}</div>
        {/* del mismo club, el club repetido no dice nada: se enseña la demarcación */}
        {isPlayer(s, type) && <div className="cm__club">{sameClub ? POSITION_ES[s.position] : s.team.name}</div>}
      </div>
    </div>
  );
}

function Row({ row, i, ca, cb }: { row: ComparisonRow; i: number; ca: string; cb: string }) {
  const max = Math.max(Math.abs(row.a.value), Math.abs(row.b.value), 1e-9);
  const wa = (Math.abs(row.a.value) / max) * 100;
  const wb = (Math.abs(row.b.value) / max) * 100;
  const aWins = row.better === "a" || row.better === "tie";
  const bWins = row.better === "b" || row.better === "tie";
  return (
    <motion.li className="cm__row" variants={rowVariants} custom={i} data-better={row.better} data-testid="cm-row">
      <span className={`cm__val cm__val--a display num${aWins ? " is-best" : ""}${row.a.display.length > 5 ? " is-long" : ""}`} style={{ "--c": ca } as CSSProperties}>{row.a.display}</span>
      <span className="cm__bar cm__bar--a">
        <motion.i className={aWins ? "is-best" : ""} style={{ width: `${wa}%`, "--c": ca, transformOrigin: "right center" } as CSSProperties} variants={growVariants} custom={i} />
      </span>
      <span className="cm__lbl caps">{row.label}</span>
      <span className="cm__bar cm__bar--b">
        <motion.i className={bWins ? "is-best" : ""} style={{ width: `${wb}%`, "--c": cb, transformOrigin: "left center" } as CSSProperties} variants={growVariants} custom={i} />
      </span>
      <span className={`cm__val cm__val--b display num${bWins ? " is-best" : ""}${row.b.display.length > 5 ? " is-long" : ""}`} style={{ "--c": cb } as CSSProperties}>{row.b.display}</span>
    </motion.li>
  );
}

/**
 * Comparativa A vs B (medio panel anclado a la derecha, entra por la derecha): los nombres se anclan al "VS", barras
 * enfrentadas que crecen desde el centro, ganador en color y perdedor legible en gris claro.
 */
export function Comparison({ payload, demoData }: GraphicProps<"comparison">) {
  const { a, b, subject_type: type, rows, headline, scope } = payload;
  const ta = teamOf(a, type);
  const tb = teamOf(b, type);
  const [ca, cb] = pairAccents(ta.colors, tb.colors);
  const crests = ta.id === tb.id ? [ta] : [ta, tb];
  return (
    <Panel
      kicker={type === "player" ? "Comparativa de jugadores" : "Comparativa de equipos"}
      headline={headline}
      team={ta}
      accent={ca}
      crest={
        <span className="cm__crests">
          {crests.map((t) => (
            <TeamCrest key={t.id} team={t} size={44} />
          ))}
        </span>
      }
      scopeLabel={scope.label}
      demoData={demoData}
      format="half"
      from="right"
      className="cmp"
      style={{ "--accent": ca, "--accent-b": cb } as CSSProperties}
    >
      <div className="cm__hero">
        <Contender s={a} type={type} color={ca} side="a" sameClub={ta.id === tb.id} />
        <div className="cm__vs display">VS</div>
        <Contender s={b} type={type} color={cb} side="b" sameClub={ta.id === tb.id} />
      </div>
      <ul className="cm__rows" aria-label="Comparativa" data-testid="cm-rows">
        {rows.map((r, i) => (
          <Row key={r.key} row={r} i={i} ca={ca} cb={cb} />
        ))}
      </ul>
    </Panel>
  );
}
