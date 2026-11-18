import { motion } from "framer-motion";
import { useMemo, type CSSProperties, type ReactNode } from "react";
import type { TeamRef } from "../contracts";
import { accentOn, edgeOn, GLASS_REF, inkOn } from "./color";
import { enterVariants, type Edge } from "./motion";
import { TeamCrest } from "./TeamCrest";
import "./Panel.css";

export function DemoBadge({ band = false }: { band?: boolean }) {
  return (
    <span className={`demo-badge caps${band ? " demo-badge--band" : ""}`} role="note" data-testid="demo-badge">
      <span className="demo-badge__dot" aria-hidden="true" />
      Datos de demostración
    </span>
  );
}

/**
 * Los tres formatos de panel (y no siete):
 *  - lower: tercio inferior, 1792 × (≤ 320). Entra desde abajo.
 *  - half:  medio panel, 1240 × (≈ 640-720).
 *  - full:  pantalla completa bajo el marcador, 1792 × 816 (anclado a top 200). Solo para repetición o descanso.
 */
export type PanelFormat = "lower" | "half" | "full";
export const PANEL_WIDTH: Record<PanelFormat, number> = { lower: 1792, half: 1240, full: 1792 };

/** Color de franja/acento cuando el grafismo no es de ningún equipo (clasificación): un neutro de marca, no el azul "sin equipo". */
export const NEUTRAL_CLUB = "#4a515e";

export interface PanelProps {
  /** Rótulo superior en versalitas: "FICHA DE JUGADOR". Siempre blanco al 85 %. */
  kicker?: string;
  /** Título a 44 px, siempre bajo el rótulo. */
  title?: ReactNode;
  /** Frase editorial: siempre bajo el título, a 32 px, máximo 2 líneas. */
  headline?: ReactNode;
  /** Contenido a la derecha de la cabecera (sustituye al escudo). */
  headRight?: ReactNode;
  /** Escudo arriba a la derecha. Por defecto el del `team`; `false` lo quita. */
  crest?: ReactNode | false;
  /** Equipo cuyo color da la franja y el acento. */
  team?: TeamRef;
  /** Acento explícito (si no hay `team`). */
  accent?: string;
  /** Colores de la franja lateral si no salen del `team` (línea de tiempo: local/visitante). */
  stripe?: [string, string];
  /** Texto de ámbito/fuente del dato: "LaLiga 2024-25 · hasta la J30". */
  scopeLabel?: string;
  /** Obligatorio pintar el distintivo cuando es true. */
  demoData: boolean;
  /** false = el grafismo pinta él mismo el distintivo (en el tercio inferior, por defecto va en la cabecera). */
  demoBadge?: boolean;
  format?: PanelFormat;
  /** Borde desde el que entra (el que toca el anclaje). */
  from?: Edge;
  /** Ancho en px lógicos (por defecto el del formato). */
  width?: number | string;
  animate?: boolean;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}

/**
 * Contenedor de grafismo: cristal oscuro, franja lateral con los colores REALES del club, cabecera fija (rótulo, título,
 * titular, escudo arriba a la derecha) y pie con ámbito + distintivo demo. En el tercio inferior el pie sube a la cabecera.
 */
export function Panel({
  kicker,
  title,
  headline,
  headRight,
  crest,
  team,
  accent,
  stripe,
  scopeLabel,
  demoData,
  demoBadge = true,
  format = "half",
  from = "left",
  width,
  animate = true,
  className,
  style,
  children,
}: PanelProps) {
  const club = team?.colors.primary ?? accent ?? NEUTRAL_CLUB;
  const club2 = team?.colors.secondary ?? club;
  const variants = useMemo(() => enterVariants(from), [from]);
  const vars = {
    "--accent": team || accent ? accentOn(club, GLASS_REF, 3) : "#f4f7fb",
    "--club": stripe?.[0] ?? edgeOn(club),
    "--club-2": stripe?.[1] ?? club2,
    "--club-fill": club,
    "--club-edge": edgeOn(club), // para filetes y barras finas (ver edgeOn)
    "--club-ink": team?.colors.text ?? inkOn(club),
    width: width ?? PANEL_WIDTH[format],
    ...style,
  } as CSSProperties;
  const crestNode = crest === false ? null : (crest ?? (team ? <TeamCrest team={team} size={48} /> : null));
  const lower = format === "lower";
  const lowerHead = lower && !!(scopeLabel || (demoData && demoBadge));
  const hasHead = !!(kicker || title || headline || headRight || lowerHead);
  const right = headRight ?? crestNode;
  return (
    <motion.section
      className={["panel", `panel--${format}`, className].filter(Boolean).join(" ")}
      style={vars}
      variants={variants}
      initial={animate ? "hidden" : false}
      animate="shown"
      exit="exit"
      data-demo={demoData ? "true" : "false"}
    >
      <div className="panel__stripe" aria-hidden="true" />
      {hasHead && (
        <header className="panel__head">
          <div className="panel__titles">
            {kicker && <div className="panel__kicker caps">{kicker}</div>}
            {title && <h2 className="panel__title display caps">{title}</h2>}
            {headline && <p className="panel__headline">{headline}</p>}
          </div>
          <div className="panel__headright">
            {lower && scopeLabel && <span className="panel__scope">{scopeLabel}</span>}
            {lower && demoData && demoBadge && <DemoBadge />}
            {right}
          </div>
        </header>
      )}
      {!hasHead && right && <div className="panel__crest">{right}</div>}
      <div className="panel__body">{children}</div>
      {!lower && (scopeLabel || demoData) && (
        <footer className="panel__foot">
          <span className="panel__scope">{scopeLabel}</span>
          {demoData && <DemoBadge />}
        </footer>
      )}
    </motion.section>
  );
}
