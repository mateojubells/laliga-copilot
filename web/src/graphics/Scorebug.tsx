import { motion } from "framer-motion";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { TeamRef } from "../contracts";
import { DemoBadge, TeamCrest, edgeOn, inkOn, wipeVariants } from "../design";
import "./Scorebug.css";
import type { GraphicProps } from "./types";

export const PERIOD_LABEL = ["Previa", "1.ª parte", "2.ª parte", "Final"] as const;

/** "67'" · "45+2'" · null cuando no corre el reloj. */
export function minuteText(minute?: number | null, added?: number | null, period?: number | null): string | null {
  if (period === 0 || period === 3 || minute == null) return null;
  return added ? `${minute}+${added}'` : `${minute}'`;
}

function Goals({ n }: { n: number }) {
  return (
    <span className="sb__goals display num" data-testid="sb-goals">
      <motion.span key={n} initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.25 }}>
        {n}
      </motion.span>
    </span>
  );
}

const teamVars = (t: TeamRef) =>
  ({ "--club-fill": t.colors.primary ?? "#445", "--club-edge": edgeOn(t.colors.primary ?? "#445"), "--club-ink": t.colors.text ?? inkOn(t.colors.primary ?? "#445") }) as CSSProperties;

/** Qué equipo acaba de marcar (null en el primer pintado): su celda se tiñe del color del club 1,2 s. */
function useScorerFlash(home: number, away: number): "home" | "away" | null {
  const prev = useRef<[number, number]>([home, away]);
  const [flash, setFlash] = useState<"home" | "away" | null>(null);
  useEffect(() => {
    const [h, a] = prev.current;
    prev.current = [home, away];
    const who = home > h ? "home" : away > a ? "away" : null;
    if (!who) return;
    setFlash(who);
    const t = setTimeout(() => setFlash(null), 1200);
    return () => clearTimeout(t);
  }, [home, away]);
  return flash;
}

/**
 * Marcador de esquina (top 64): celdas de equipo con el color del club (fondo al 35 % + filete inferior de 6 px),
 * goles, reloj y, pegada debajo, la banda de datos de demostración. Entra con un barrido horizontal.
 */
export function Scorebug({ payload, demoData }: GraphicProps<"scorebug">) {
  const { home, away, home_goals, away_goals, minute, period, added } = payload;
  const clock = minuteText(minute, added, period);
  // con el reloj parado (previa, final) se muestra el periodo en su lugar; con el reloj en marcha, el reloj lo dice todo
  const label = !clock && period != null ? (PERIOD_LABEL[period] ?? null) : null;
  const flash = useScorerFlash(home_goals, away_goals);
  return (
    <motion.div className="sb-wrap" variants={wipeVariants} initial="hidden" animate="shown" exit="exit" data-demo={demoData ? "true" : "false"}>
      <div className={`sb${demoData ? " sb--demo" : ""}`} role="group" aria-label={`${home.name} ${home_goals}, ${away.name} ${away_goals}`}>
        <div className={`sb__team sb__team--home${flash === "home" ? " is-flash" : ""}`} style={teamVars(home)}>
          <TeamCrest team={home} size={44} />
          <b className="sb__abbr display caps" data-testid="sb-home">{home.short}</b>
        </div>
        <div className="sb__score">
          <Goals n={home_goals} />
          <i className="sb__sep">–</i>
          <Goals n={away_goals} />
        </div>
        <div className={`sb__team sb__team--away${flash === "away" ? " is-flash" : ""}`} style={teamVars(away)}>
          <b className="sb__abbr display caps" data-testid="sb-away">{away.short}</b>
          <TeamCrest team={away} size={44} />
        </div>
        <div className="sb__time" data-testid="sb-time">
          {clock ? <b className="sb__min display num">{clock}</b> : null}
          {label && <span className="sb__period caps">{label}</span>}
        </div>
      </div>
      {demoData && <DemoBadge band />}
    </motion.div>
  );
}
