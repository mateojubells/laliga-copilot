import { motion } from "framer-motion";
import { accentOn, growVariants } from "../design";
import { AttackArrow, HeatLayer, Pitch, ThirdsLines, thirdsShare } from "../pitch";
import "./HeatMap.css";
import { FIELD_PAD, FIELD_TOP_BAND, FieldShell, Reveal, fmtInt, nameOfSubject, teamOfSubject } from "./shared";
import type { GraphicProps } from "./types";

const PITCH_W = 660;

export const METRIC_LABEL = {
  touches: "Toques",
  recoveries: "Recuperaciones",
  passes_received: "Pases recibidos",
  shots: "Tiros",
} as const;

const THIRD_NAME = ["Defensa", "Medio", "Ataque"] as const;

/** Mapa de calor: rejilla suavizada a campo completo, sentido de ataque, métrica total y reparto por tercios (suma 100 %). */
export function HeatMap({ payload, demoData }: GraphicProps<"heat_map">) {
  const { subject, subject_type: type, metric = "touches", grid, cols, rows, total, headline, scope } = payload;
  const team = teamOfSubject(subject, type);
  const name = nameOfSubject(subject, type);
  const label = METRIC_LABEL[metric];
  // zonas excluyentes (tercios), calculadas de la propia rejilla: así la barra suma 100 y respalda las líneas del campo
  const thirds = thirdsShare(grid, cols, rows);
  const biggest = thirds.indexOf(Math.max(...thirds));
  return (
    <FieldShell
      kicker={`Mapa de calor · ${label}`}
      title={name}
      headline={headline}
      team={team}
      scope={scope.label}
      demoData={demoData}
      pitchW={PITCH_W}
      className="hm"
      pitch={
        <Pitch width={PITCH_W} padding={FIELD_PAD} topBand={FIELD_TOP_BAND} accent={accentOn(team.colors.primary ?? "#7cc4ff")} label={`Mapa de calor de ${name}`}>
          <HeatLayer grid={grid} cols={cols} rows={rows} />
          <ThirdsLines />
          <AttackArrow />
        </Pitch>
      }
      side={
        <>
          <Reveal className="hm__total">
            <div className="sd__label">{label} en total</div>
            <div className="hm__total-v display num" data-testid="hm-total">{fmtInt(total)}</div>
          </Reveal>
          <Reveal className="hm__zones">
            <div className="sd__label">Por tercios del campo</div>
            <div className="hm__stack" role="img" aria-label={THIRD_NAME.map((n, i) => `${n} ${thirds[i]} %`).join(", ")}>
              {thirds.map((v, i) =>
                v > 0 ? (
                  <motion.i
                    key={i}
                    className={i === biggest ? "is-big" : ""}
                    style={{ flexGrow: v, transformOrigin: "left center" }}
                    variants={growVariants}
                    custom={i}
                  />
                ) : null,
              )}
            </div>
            <ul className="hm__list" data-testid="hm-zones">
              {thirds.map((v, i) => (
                <li key={i} className={`hm__zone${i === biggest ? " is-big" : ""}`}>
                  <span>{THIRD_NAME[i]}</span>
                  <b className="hm__zone-v display num">{v} %</b>
                </li>
              ))}
            </ul>
          </Reveal>
        </>
      }
    />
  );
}
