import type { ReactNode } from "react";

export type EventKind =
  | "gol" | "penalti" | "amarilla" | "roja" | "cambio" | "corner" | "falta" | "parada" | "tiro" | "regate"
  | "fuera_de_juego" | "var" | "lesion" | "palo" | "otro";

const ALIASES: Record<string, EventKind> = {
  gol: "gol", goal: "gol", penalti: "penalti", penalty: "penalti", amarilla: "amarilla", yellow: "amarilla",
  roja: "roja", red: "roja", cambio: "cambio", sustitucion: "cambio", corner: "corner", falta: "falta", foul: "falta",
  parada: "parada", save: "parada", tiro: "tiro", shot: "tiro", remate: "tiro", regate: "regate", fuera_de_juego: "fuera_de_juego",
  fuera: "fuera_de_juego", offside: "fuera_de_juego", var: "var", lesion: "lesion", palo: "palo", poste: "palo",
};

/** Normaliza el `type` libre del contrato ("córner", "Fuera de juego"…) a un icono conocido. */
export function eventKind(type: string): EventKind {
  const k = type.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim().replace(/[\s-]+/g, "_");
  return ALIASES[k] ?? "otro";
}

export const EVENT_NAME: Record<EventKind, string> = {
  gol: "Gol", penalti: "Penalti", amarilla: "Tarjeta amarilla", roja: "Tarjeta roja", cambio: "Cambio", corner: "Córner",
  falta: "Falta", parada: "Parada", tiro: "Tiro", regate: "Regate", fuera_de_juego: "Fuera de juego", var: "VAR",
  lesion: "Lesión", palo: "Palo", otro: "Evento",
};

const INK = "#f4f7fb";
const DARK = "#05080e";

/** Pelota: círculo blanco con pentágono central y costuras. */
function Ball({ cx = 24, cy = 24, r = 14 }: { cx?: number; cy?: number; r?: number }) {
  const pent = Array.from({ length: 5 }, (_, i) => {
    const a = (-90 + i * 72) * (Math.PI / 180);
    return [cx + Math.cos(a) * r * 0.5, cy + Math.sin(a) * r * 0.5] as const;
  });
  return (
    <g>
      <circle cx={cx} cy={cy} r={r} fill="#fff" stroke={DARK} strokeWidth={1.8} />
      <polygon points={pent.map((p) => p.join(",")).join(" ")} fill={DARK} />
      {pent.map(([px, py], i) => {
        const a = (-90 + i * 72) * (Math.PI / 180);
        return <line key={i} x1={px} y1={py} x2={cx + Math.cos(a) * r * 0.98} y2={cy + Math.sin(a) * r * 0.98} stroke={DARK} strokeWidth={1.8} />;
      })}
    </g>
  );
}

const GLYPH: Record<EventKind, () => ReactNode> = {
  gol: () => <Ball />,
  penalti: () => (
    <g fill="none" stroke={INK} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 36 V14 H38 V36" />
      <circle cx={24} cy={30} r={4.2} fill="#fff" stroke={DARK} strokeWidth={1.5} />
    </g>
  ),
  amarilla: () => <rect x={15} y={9} width={18} height={26} rx={3} fill="#ffd23f" stroke={DARK} strokeWidth={1.5} transform="rotate(8 24 24)" />,
  roja: () => <rect x={15} y={9} width={18} height={26} rx={3} fill="#ff4d5e" stroke={DARK} strokeWidth={1.5} transform="rotate(8 24 24)" />,
  cambio: () => (
    <g strokeLinejoin="round" strokeLinecap="round" strokeWidth={2.5} stroke={DARK}>
      <path d="M17 8 L26 20 H20 V34 H14 V20 H8 Z" fill="#3ddc97" transform="translate(2 -1)" />
      <path d="M31 40 L22 28 H28 V14 H34 V28 H40 Z" fill="#ff6b7a" transform="translate(-2 1)" />
    </g>
  ),
  corner: () => (
    <g strokeLinejoin="round" strokeLinecap="round">
      <path d="M16 38 V10" stroke={INK} strokeWidth={3.5} fill="none" />
      <polygon points="16,10 35,16.5 16,23" fill="#ffd23f" stroke={DARK} strokeWidth={1.5} />
    </g>
  ),
  falta: () => (
    <g fill="none" stroke={INK} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
      <circle cx={19} cy={29} r={8} />
      <path d="M26 22 L38 13 M12 20 H25" />
    </g>
  ),
  parada: () => (
    <g fill={INK} stroke={DARK} strokeWidth={1.3} strokeLinejoin="round">
      <rect x={11} y={11} width={5.5} height={15} rx={2.7} />
      <rect x={17.5} y={7} width={5.5} height={19} rx={2.7} />
      <rect x={24} y={9} width={5.5} height={17} rx={2.7} />
      <rect x={30.5} y={13} width={5.5} height={13} rx={2.7} />
      <path d="M11 24 H36 V31 Q36 39 27 39 H20 Q11 39 11 30 Z" />
    </g>
  ),
  tiro: () => (
    <g>
      <Ball cx={30} cy={24} r={10} />
      <g stroke={INK} strokeWidth={3} strokeLinecap="round">
        <path d="M6 17 H16 M4 24 H14 M6 31 H16" />
      </g>
    </g>
  ),
  regate: () => (
    <g fill="none" stroke={INK} strokeWidth={3.2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 34 L19 15 L27 32 L37 13" />
      <path d="M30 12 L38 12 L38 20" />
    </g>
  ),
  fuera_de_juego: () => (
    <g strokeLinejoin="round" strokeLinecap="round">
      <path d="M15 40 V8" stroke={INK} strokeWidth={3.5} fill="none" />
      <rect x={15} y={8} width={20} height={14} fill="#ffd23f" stroke={DARK} strokeWidth={1.5} />
      <path d="M15 22 L35 8" stroke={DARK} strokeWidth={2} />
    </g>
  ),
  var: () => (
    <g>
      <rect x={6} y={13} width={36} height={22} rx={4} fill="none" stroke={INK} strokeWidth={2.8} />
      <text x={24} y={30} textAnchor="middle" fontFamily="var(--font-display)" fontWeight={800} fontSize={17} fill={INK}>VAR</text>
    </g>
  ),
  lesion: () => <path d="M19 8 H29 V19 H40 V29 H29 V40 H19 V29 H8 V19 H19 Z" fill="#ff4d5e" stroke={DARK} strokeWidth={1.5} strokeLinejoin="round" />,
  palo: () => (
    <g>
      <rect x={30} y={6} width={6} height={36} rx={2} fill={INK} stroke={DARK} strokeWidth={1.3} />
      <Ball cx={19} cy={24} r={9} />
    </g>
  ),
  otro: () => <circle cx={24} cy={24} r={7} fill={INK} />,
};

export type EventStatus = "auto" | "approved" | "edited" | "discarded";

/**
 * Icono de evento dibujado en SVG propio: disco oscuro con aro del color del equipo y glifo por tipo.
 *
 * En ANTENA (`editorial` false, por defecto) el icono no lleva ninguna marca de estado: aro continuo, sin ✓, sin lápiz,
 * sin aro discontinuo, sin tachado, y las tarjetas son un rectángulo sólido sin disco. Los estados de moderación son UI
 * de operador y solo se pintan con `editorial`: auto = aro discontinuo (detectado, sin confirmar) · approved = ✓ verde ·
 * edited = punto azul · discarded = apagado y tachado.
 */
export function EventIcon({
  type, size = 44, color = "#7cc4ff", status = "auto", editorial = false,
}: { type: string; size?: number; color?: string; status?: EventStatus; editorial?: boolean }) {
  const kind = eventKind(type);
  const card = !editorial && (kind === "amarilla" || kind === "roja");
  const mark = editorial ? status : undefined;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label={EVENT_NAME[kind]}
      data-icon={kind}
      data-status={editorial ? status : undefined}
      style={{ display: "block", flex: "none", opacity: mark === "discarded" ? 0.4 : 1, overflow: "visible" }}
    >
      {card ? (
        // tarjeta de antena: rectángulo sólido de 20×28 (a 48 u), sin círculo
        <rect x={14} y={10} width={20} height={28} rx={3} fill={kind === "amarilla" ? "#ffd23f" : "#ff4d5e"} stroke={DARK} strokeWidth={2} />
      ) : (
        <>
          <circle cx={24} cy={24} r={22} fill="rgba(5,8,14,0.94)" stroke={color} strokeWidth={3} strokeDasharray={mark === "auto" ? "6 4" : undefined} />
          <g transform="translate(5 5) scale(0.79)">{GLYPH[kind]()}</g>
        </>
      )}
      {mark === "approved" && (
        <g transform="translate(35 35)">
          <circle r={9} fill="#3ddc97" stroke={DARK} strokeWidth={2} />
          <path d="M-4.5 0 L-1.5 3.2 L4.5 -3.2" fill="none" stroke={DARK} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
        </g>
      )}
      {mark === "edited" && (
        <g transform="translate(35 35)">
          <circle r={9} fill="#7cc4ff" stroke={DARK} strokeWidth={2} />
          <path d="M-3.5 3.5 L-3 0.5 L2.5 -5 L5 -2.5 L-0.5 3 Z" fill={DARK} />
        </g>
      )}
      {mark === "discarded" && <path d="M6 42 L42 6" stroke="#ff6b7a" strokeWidth={4} strokeLinecap="round" />}
    </svg>
  );
}
