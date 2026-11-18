import { useId, useState } from "react";
import type { PlayerRef } from "../contracts";
import { mix } from "./color";
import { useImageMode } from "./ImageSource";

/** Avatar generado: silueta + dorsal + colores del club. NO es una foto del jugador. */
export function GeneratedAvatar({ player, size }: { player: PlayerRef; size: number }) {
  const uid = useId().replace(/:/g, "");
  const { primary = "#445566", secondary = "#ffffff" } = player.team.colors;
  const dark = mix(primary, "#05080e", 0.55);
  const light = mix(primary, "#ffffff", 0.12);
  const num = player.number;
  return (
    <svg
      role="img"
      aria-label={`Avatar de ${player.known_as}`}
      data-testid="avatar-generated"
      width={size}
      height={size}
      viewBox="0 0 120 120"
      style={{ display: "block", flex: "none", borderRadius: "50%" }}
    >
      <defs>
        <clipPath id={`ac-${uid}`}>
          <circle cx="60" cy="60" r="60" />
        </clipPath>
        <linearGradient id={`ag-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={light} />
          <stop offset="1" stopColor={dark} />
        </linearGradient>
      </defs>
      <g clipPath={`url(#ac-${uid})`}>
        <rect width="120" height="120" fill={`url(#ag-${uid})`} />
        {/* silueta: hombros y cabeza */}
        <path d="M14 124 C14 92 34 82 60 82 C86 82 106 92 106 124 Z" fill={mix(primary, "#05080e", 0.72)} />
        <path d="M46 84 L60 98 L74 84 Z" fill={secondary} opacity="0.9" />
        <circle cx="60" cy="52" r="20" fill={mix(primary, "#05080e", 0.62)} />
        {num != null && (
          <text
            x="60"
            y="112"
            textAnchor="middle"
            fontFamily="var(--font-display)"
            fontWeight="800"
            fontSize="30"
            fill="#fff"
            stroke="rgba(0,0,0,0.55)"
            strokeWidth="3"
            paintOrder="stroke"
          >
            {num}
          </text>
        )}
      </g>
      <circle cx="60" cy="60" r="58" fill="none" stroke={secondary} strokeOpacity="0.7" strokeWidth="3" />
    </svg>
  );
}

export function PlayerAvatar({ player, size = 120 }: { player: PlayerRef; size?: number }) {
  const mode = useImageMode();
  const [failed, setFailed] = useState(false);
  if (mode === "remote" && player.avatar && !failed) {
    return (
      <img
        src={player.avatar}
        alt={`Avatar de ${player.known_as}`}
        width={size}
        height={size}
        style={{ display: "block", flex: "none", borderRadius: "50%", objectFit: "cover" }}
        onError={() => setFailed(true)}
      />
    );
  }
  return <GeneratedAvatar player={player} size={size} />;
}
