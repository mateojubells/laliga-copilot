import { useId, useState } from "react";
import type { TeamRef } from "../contracts";
import { inkOn, mix } from "./color";
import { useImageMode } from "./ImageSource";

/** Siglas para el escudo: el `short` si es corto (BAR), si no las 3 primeras letras. */
export function crestInitials(team: Pick<TeamRef, "short" | "name">): string {
  const s = (team.short || team.name).trim();
  return (s.length <= 4 ? s : s.slice(0, 3)).toUpperCase();
}

const SHIELD = "M6 6 H94 V70 C94 96 70 112 50 120 C30 112 6 96 6 70 Z";

/** Escudo esquemático generado (no es el escudo real del club): cabecera con siglas + franjas verticales. */
export function GeneratedCrest({ team, size }: { team: TeamRef; size: number }) {
  const uid = useId().replace(/:/g, "");
  const primary = team.colors.primary ?? "#445";
  const secondary = team.colors.secondary ?? "#fff";
  const ink = team.colors.text ?? inkOn(primary);
  const text = initialsFit(crestInitials(team));
  const stripeA = primary;
  const stripeB = secondary;
  return (
    <svg
      role="img"
      aria-label={`Escudo de ${team.name}`}
      data-testid="crest-generated"
      width={size}
      height={size * 1.2}
      viewBox="0 0 100 120"
      style={{ display: "block", flex: "none" }}
    >
      <defs>
        <clipPath id={`cc-${uid}`}>
          <path d={SHIELD} />
        </clipPath>
        <linearGradient id={`cg-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.22" />
          <stop offset="0.5" stopColor="#fff" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.28" />
        </linearGradient>
      </defs>
      <g clipPath={`url(#cc-${uid})`}>
        <rect x="0" y="0" width="100" height="120" fill={stripeA} />
        {[1, 3, 5].map((i) => (
          <rect key={i} x={6 + i * (88 / 6)} y="52" width={88 / 6} height="70" fill={stripeB} />
        ))}
        <rect x="0" y="0" width="100" height="52" fill={mix(primary, "#000", 0.15)} />
        <rect x="0" y="50" width="100" height="3" fill={stripeB} />
        <rect x="0" y="0" width="100" height="120" fill={`url(#cg-${uid})`} />
      </g>
      <path d={SHIELD} fill="none" stroke="rgba(255,255,255,0.85)" strokeWidth="4" strokeLinejoin="round" />
      <text
        x="50"
        y="38"
        textAnchor="middle"
        fontFamily="var(--font-display)"
        fontWeight="800"
        fontSize={text.size}
        fill={ink}
        letterSpacing="1"
      >
        {text.value}
      </text>
    </svg>
  );
}

function initialsFit(v: string) {
  return { value: v, size: v.length <= 2 ? 34 : v.length === 3 ? 29 : 24 };
}

/** Escudo: URL del contrato con caída al SVG generado. `size` = ancho en px. */
export function TeamCrest({ team, size = 64 }: { team: TeamRef; size?: number }) {
  const mode = useImageMode();
  const [failed, setFailed] = useState(false);
  if (mode === "remote" && team.crest && !failed) {
    return (
      <img
        src={team.crest}
        alt={`Escudo de ${team.name}`}
        width={size}
        height={size * 1.2}
        style={{ display: "block", flex: "none", objectFit: "contain" }}
        onError={() => setFailed(true)}
      />
    );
  }
  return <GeneratedCrest team={team} size={size} />;
}
