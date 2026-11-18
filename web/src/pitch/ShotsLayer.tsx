import { motion } from "framer-motion";
import type { Shot } from "../contracts";
import { popVariants } from "../design/motion";
import { usePitch } from "./context";

export const SHOT_OUTCOME_LABEL: Record<Shot["outcome"], string> = {
  goal: "Gol",
  saved: "Parado",
  off: "Fuera",
  blocked: "Bloqueado",
  post: "Palo",
};

/**
 * Radio (metros) de un tiro según su xG: el ÁREA es proporcional al xG (r = 3,2·√xG) con un mínimo para que el
 * tiro de 0,02 siga viéndose. Compartido con las leyendas.
 */
export function shotRadiusM(xg: number): number {
  return Math.max(0.7, 3.2 * Math.sqrt(Math.max(0, xg)));
}

export interface ShotStyle {
  fill: string;
  fillOpacity: number;
  stroke: string;
  strokeWidth: number;
  dash?: string;
  /** Aspa × dentro del círculo (bloqueado). */
  cross?: boolean;
}

/** Radio de un tiro (px): entre 8 y 16. Con ~7 px/m no caben radios mayores en el área pequeña sin que los goles se pisen. */
export const SHOT_R_MIN = 8;
export const SHOT_R_MAX = 16;
export const GOAL_R_MAX = SHOT_R_MAX;
const OUTLINE = "#0b1018";

/**
 * Estilo por resultado, distinguible a 3 m: gol = relleno del color del club con aro blanco de 2 px (el más reciente, de 3 px y un segundo aro); parado = relleno gris sólido; fuera = aro fino al 55 %; bloqueado = aspa ×; palo = dorado.
 */
export function shotStyle(outcome: Shot["outcome"], accent: string): ShotStyle {
  switch (outcome) {
    case "goal":
      // relleno del color OFICIAL del club (el mismo de la tile GOLES) con aro blanco de 2 px; el último gol, de 3 px
      return { fill: `var(--club-fill, ${accent})`, fillOpacity: 1, stroke: "#ffffff", strokeWidth: 2 };
    case "saved":
      return { fill: "#a3adbd", fillOpacity: 1, stroke: "rgba(255,255,255,0.95)", strokeWidth: 2 };
    case "off":
      return { fill: "rgba(255,255,255,0)", fillOpacity: 1, stroke: "rgba(255,255,255,0.55)", strokeWidth: 2.5 };
    case "blocked":
      return { fill: "rgba(255,255,255,0.06)", fillOpacity: 1, stroke: "rgba(255,255,255,0.8)", strokeWidth: 2, cross: true };
    case "post":
      return { fill: "rgba(255,194,71,0.28)", fillOpacity: 1, stroke: "#ffc247", strokeWidth: 4 };
  }
}

function Cross({ r, cx = 0, cy = 0 }: { r: number; cx?: number; cy?: number }) {
  const d = r * 0.5;
  return <path d={`M ${cx - d} ${cy - d} L ${cx + d} ${cy + d} M ${cx - d} ${cy + d} L ${cx + d} ${cy - d}`} stroke="rgba(255,255,255,0.9)" strokeWidth={2.5} strokeLinecap="round" fill="none" />;
}

/** Muestra de un resultado para las leyendas (SVG propio, mismo estilo que el campo). */
export function ShotGlyph({ outcome, r = 14, accent = "#7cc4ff" }: { outcome: Shot["outcome"]; r?: number; accent?: string }) {
  const st = shotStyle(outcome, accent);
  const size = (r + 6) * 2;
  return (
    <svg width={size} height={size} viewBox={`${-size / 2} ${-size / 2} ${size} ${size}`} aria-hidden="true" style={{ flex: "none" }}>
      <circle r={r} fill={st.fill} fillOpacity={st.fillOpacity} stroke={st.stroke} strokeWidth={st.strokeWidth} strokeDasharray={st.dash} />
      {st.cross && <Cross r={r} />}
    </svg>
  );
}

/**
 * Tiros: círculo con área ∝ xG (radio entre 8 y 16 px); los goles van rellenos con el color del club, aro blanco y un
 * contorno oscuro exterior, dibujados al final; el más reciente lleva un aro blanco más grueso. Aparecen escalonados. `dotRadius` fija un radio único (mini-campos).
 */
export function ShotsLayer({ shots, legend = true, dotRadius }: { shots: readonly Shot[]; legend?: boolean; dotRadius?: number }) {
  const { x, y, k, accent, height, bottom, width } = usePitch();
  // los goles se pintan encima
  const ordered = [...shots].sort((a, b) => Number(a.outcome === "goal") - Number(b.outcome === "goal"));
  const lastGoal = shots.filter((s) => s.outcome === "goal").reduce<Shot | null>((m, s) => (!m || s.minute > m.minute ? s : m), null);
  const ly = height - bottom / 2;
  const radius = (s: Shot) => {
    if (dotRadius) return dotRadius;
    return Math.min(SHOT_R_MAX, Math.max(SHOT_R_MIN, shotRadiusM(s.xg) * k));
  };
  return (
    <g data-layer="shots">
      {ordered.map((s, i) => {
        const st = shotStyle(s.outcome, accent);
        const r = radius(s);
        return (
          <motion.g key={i} variants={popVariants} custom={i}>
            {s.outcome === "goal" && <circle cx={x(s.x)} cy={y(s.y)} r={r + 1} fill="none" stroke={OUTLINE} strokeWidth={s === lastGoal ? 6 : 4} strokeOpacity={0.9} />}
            <circle
              data-shot={s.outcome}
              data-xg={s.xg}
              cx={x(s.x)}
              cy={y(s.y)}
              r={r}
              fill={st.fill}
              fillOpacity={st.fillOpacity}
              stroke={st.stroke}
              strokeWidth={s === lastGoal ? 3 : st.strokeWidth}
              strokeDasharray={st.dash}
            >
              <title>{`${s.player_name} ${s.minute}' · ${SHOT_OUTCOME_LABEL[s.outcome]} · xG ${s.xg.toFixed(2)}`}</title>
            </circle>
            {st.cross && <Cross r={r} cx={x(s.x)} cy={y(s.y)} />}
          </motion.g>
        );
      })}
      {legend && bottom >= 48 && (
        <g data-layer="shots-legend" fontFamily="var(--font-text)" fontSize={24} fill="var(--c-text-2)">
          <circle cx={x(2)} cy={ly} r={11} fill={`var(--club-fill, ${accent})`} stroke="#fff" strokeWidth={2} />
          <text x={x(2) + 22} y={ly + 8}>Gol</text>
          <circle cx={x(12)} cy={ly} r={11} fill="#a3adbd" stroke="rgba(255,255,255,0.95)" strokeWidth={2} />
          <text x={x(12) + 22} y={ly + 8}>Parado</text>
          <circle cx={x(32)} cy={ly} r={11} fill="none" stroke="rgba(255,255,255,0.8)" strokeWidth={2} />
          <Cross r={11} cx={x(32)} cy={ly} />
          <text x={x(32) + 22} y={ly + 8}>Bloqueado</text>
          <g transform={`translate(${width - 330} ${ly})`}>
            <circle cx={0} cy={0} r={Math.max(SHOT_R_MIN, shotRadiusM(0.05) * k)} fill="none" stroke="rgba(255,255,255,0.78)" strokeWidth={2} />
            <circle cx={44} cy={0} r={Math.max(SHOT_R_MIN, shotRadiusM(0.3) * k)} fill="none" stroke="rgba(255,255,255,0.78)" strokeWidth={2} />
            <circle cx={104} cy={0} r={Math.max(SHOT_R_MIN, shotRadiusM(0.76) * k)} fill="none" stroke="rgba(255,255,255,0.78)" strokeWidth={2} />
            <text x={146} y={8}>tamaño = xG</text>
          </g>
        </g>
      )}
    </g>
  );
}
