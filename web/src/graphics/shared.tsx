import { motion } from "framer-motion";
import type { CSSProperties, ReactNode } from "react";
import type { PlayerRef, TeamRef } from "../contracts";
import { itemVariants, Panel, TeamCrest, type Edge } from "../design";
import "./Field.css";

const PARTICLES = new Set(["de", "da", "do", "dos", "del", "di", "van", "von", "el", "al", "le", "la", "ter"]);

/** Apellido para etiquetas cortas: "Íñigo Martínez" → "Martínez", "Dani Olmo" → "Olmo", "De Jong" → "De Jong". */
export function surname(p: Pick<PlayerRef, "known_as">): string {
  const parts = p.known_as.trim().split(/\s+/);
  if (parts.length === 1) return parts[0]!;
  if (PARTICLES.has(parts[0]!.toLowerCase())) return parts.join(" ");
  // "Marc-André ter Stegen" → "ter Stegen": las partículas que preceden al último apellido se quedan con él
  let i = parts.length - 1;
  while (i > 1 && PARTICLES.has(parts[i - 1]!.toLowerCase())) i--;
  return parts.slice(i).join(" ");
}

/** 1842 → "1.842" (separador de millares español). */
export const fmtInt = (n: number): string => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");

const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
/** "2025-01-12" → "12 ene 2025". */
export function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export const teamOfSubject = (s: PlayerRef | TeamRef, type: "player" | "team"): TeamRef =>
  type === "player" ? (s as PlayerRef).team : (s as TeamRef);
export const nameOfSubject = (s: PlayerRef | TeamRef, type: "player" | "team"): string =>
  type === "player" ? (s as PlayerRef).known_as : (s as TeamRef).name;

/** Bloque de contenido que entra escalonado con el grafismo. */
export function Reveal({
  children,
  className,
  style,
  "data-testid": testId,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  "data-testid"?: string;
}) {
  return (
    <motion.div className={className} style={style} variants={itemVariants} data-testid={testId}>
      {children}
    </motion.div>
  );
}

/** Banda libre sobre el campo (fuera del césped) para el sentido de ataque: igual en los cuatro grafismos de campo. */
export const FIELD_TOP_BAND = 60;
/** Margen del campo y ancho útil de cada formato. */
export const FIELD_PAD = 24;
export const INNER_W = { half: 1168, full: 1720 } as const;

/**
 * Plantilla común de los grafismos de campo: Panel de medio panel (1240) o pantalla completa (1792) con el campo a un
 * lado y la columna de datos al otro. La cabecera (rótulo, título, titular) va en la columna de datos para dejar todo
 * el alto al campo; el escudo, siempre arriba a la derecha del panel. El campo lleva el sentido de ataque en su banda
 * superior (fuera del césped) y la leyenda va siempre en la columna, nunca sobre el césped.
 * `pitchW` es el ancho del campo en px lógicos (= ancho de su viewBox: 1 unidad = 1 px).
 */
export function FieldShell({
  kicker,
  title,
  headline,
  team,
  scope,
  demoData,
  pitch,
  side,
  pitchW,
  pitchSide = "left",
  format = "half",
  from = "left",
  className,
}: {
  kicker: string;
  title: ReactNode;
  headline?: ReactNode;
  team: TeamRef;
  scope: string;
  demoData: boolean;
  pitch: ReactNode;
  side: ReactNode;
  pitchW: number;
  pitchSide?: "left" | "right";
  format?: "half" | "full";
  from?: Edge;
  className?: string;
}) {
  const head = (
    <header className="fs__head">
      <div className="panel__kicker caps">{kicker}</div>
      <h2 className="panel__title display caps">{title}</h2>
      {headline && <p className="panel__headline">{headline}</p>}
    </header>
  );
  const cols = pitchSide === "left" ? `${pitchW}px minmax(0, 1fr)` : `minmax(0, 1fr) ${pitchW}px`;
  return (
    <Panel
      crest={<TeamCrest team={team} size={48} />}
      team={team}
      scopeLabel={scope}
      demoData={demoData}
      format={format}
      from={from}
      className={`fs fs--${format} ${className ?? ""}`}
    >
      <div className="fs__grid" style={{ gridTemplateColumns: cols }}>
        {pitchSide === "right" && (
          <div className="fs__side">
            {head}
            {side}
          </div>
        )}
        <div className="fs__pitch">{pitch}</div>
        {pitchSide === "left" && (
          <div className="fs__side">
            {head}
            {side}
          </div>
        )}
      </div>
    </Panel>
  );
}
