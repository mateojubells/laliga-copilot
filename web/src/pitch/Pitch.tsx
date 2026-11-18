import { scaleLinear } from "d3-scale";
import { useId, useMemo, type ReactNode } from "react";
import { PitchContext, type PitchCtx } from "./context";
import { arcPath, centeredSpan, PITCH, penaltyArcHalfChord } from "./geometry";

/** Recorte del campo en metros (zoom): lo que queda fuera del recorte no se dibuja; los bordes recortados sangran hasta el SVG. */
export interface PitchView {
  x0?: number;
  x1?: number;
  y0?: number;
  y1?: number;
}

export interface PitchProps {
  /** Recorte (p. ej. medio campo atacante `{ x0: 44 }`). Por defecto el campo entero. */
  view?: PitchView;
  /** Ancho del viewBox en px lógicos (el SVG escala al 100 % del contenedor). */
  width?: number;
  /** Margen alrededor del campo (cabe la portería y los dorsales de los bordes). */
  padding?: number;
  /** Banda libre bajo el campo para leyendas. */
  bottomBand?: number;
  /** Banda libre sobre el campo (fuera del césped): sentido de ataque. */
  topBand?: number;
  accent?: string;
  label?: string;
  children?: ReactNode;
}

const STRIPES = 14;

/**
 * Campo 105×68 m en SVG, horizontal, tema oscuro. Origen de datos abajo-izquierda; el ataque va hacia x creciente.
 * Las capas hijas leen las escalas con usePitch().
 */
export function Pitch({
  view,
  width = 1110,
  padding = 30,
  bottomBand = 0,
  topBand = 0,
  accent = "#7cc4ff",
  label = "Campo de fútbol",
  children,
}: PitchProps) {
  const uid = useId().replace(/:/g, "");
  const vx0 = view?.x0 ?? 0;
  const vx1 = view?.x1 ?? PITCH.length;
  const vy0 = view?.y0 ?? 0;
  const vy1 = view?.y1 ?? PITCH.width;
  const ctx = useMemo<PitchCtx>(() => {
    // solo hay margen en los lados donde el campo termina de verdad; en los recortados el césped sangra
    const padL = vx0 <= 0 ? padding : 0;
    const padR = vx1 >= PITCH.length ? padding : 0;
    const padT = vy1 >= PITCH.width ? padding : 0;
    const padB = vy0 <= 0 ? padding : 0;
    const k = (width - padL - padR) / (vx1 - vx0);
    const x = scaleLinear().domain([vx0, vx1]).range([padL, padL + (vx1 - vx0) * k]);
    const y = scaleLinear().domain([vy0, vy1]).range([topBand + padT + (vy1 - vy0) * k, topBand + padT]);
    const height = topBand + padT + padB + (vy1 - vy0) * k + bottomBand;
    return { x, y, k, width, height, pad: padding, bottom: bottomBand, top: topBand, accent };
  }, [width, padding, bottomBand, topBand, accent, vx0, vx1, vy0, vy1]);

  const { x, y, k, height } = ctx;
  const goalExt = PITCH.goal.depth * k; // la portería sobresale de la línea de fondo
  const cropped = vx0 > 0 || vx1 < PITCH.length || vy0 > 0 || vy1 < PITCH.width;
  const X = (m: number) => x(m);
  const Y = (m: number) => y(m);
  const S = (m: number) => m * k;
  const line = { stroke: "var(--c-pitch-line)", strokeWidth: 2.5, fill: "none", strokeLinejoin: "round" as const };

  const [paT, paB] = centeredSpan(PITCH.penaltyArea.width); // y bajo / alto del área grande
  const [gaT, gaB] = centeredSpan(PITCH.goalArea.width);
  const [goalLo, goalHi] = centeredSpan(PITCH.goal.width);
  const halfChord = penaltyArcHalfChord();
  const mid = PITCH.width / 2;

  const sides = (["left", "right"] as const).map((side) => {
    const sgn = side === "left" ? 1 : -1;
    const x0 = side === "left" ? 0 : PITCH.length; // línea de fondo
    const at = (d: number) => x0 + sgn * d; // metros hacia dentro del campo
    const rect = (depth: number, lo: number, hi: number) => ({
      x: Math.min(X(x0), X(at(depth))),
      y: Y(hi),
      width: S(depth),
      height: S(hi - lo),
    });
    const spot = { x: X(at(PITCH.penaltySpot)), y: Y(mid) };
    const arcS = { x: X(at(PITCH.penaltyArea.depth)), y: Y(mid + halfChord) };
    const arcE = { x: X(at(PITCH.penaltyArea.depth)), y: Y(mid - halfChord) };
    return {
      side,
      penalty: rect(PITCH.penaltyArea.depth, paT, paB),
      goalArea: rect(PITCH.goalArea.depth, gaT, gaB),
      goal: {
        x: side === "left" ? X(0) - S(PITCH.goal.depth) : X(PITCH.length),
        y: Y(goalHi),
        width: S(PITCH.goal.depth),
        height: S(goalHi - goalLo),
      },
      spot,
      arc: arcPath(spot, arcS, arcE, S(PITCH.penaltyArcRadius)),
    };
  });

  const corners = ([0, PITCH.length] as const).flatMap((cx) =>
    ([0, PITCH.width] as const).map((cy) => {
      const dx = cx === 0 ? 1 : -1;
      const dy = cy === 0 ? 1 : -1;
      const c = { x: X(cx), y: Y(cy) };
      const r = S(PITCH.cornerRadius);
      // dy en metros crece hacia arriba; en píxeles el signo se invierte
      return {
        key: `${cx}-${cy}`,
        d: arcPath(c, { x: X(cx + dx * PITCH.cornerRadius), y: Y(cy) }, { x: X(cx), y: Y(cy + dy * PITCH.cornerRadius) }, r),
      };
    }),
  );

  const stripeW = PITCH.length / STRIPES;
  return (
    <PitchContext.Provider value={ctx}>
      <svg
        viewBox={`0 0 ${ctx.width} ${height}`}
        width="100%"
        style={{ display: "block", height: "auto" }}
        role="img"
        aria-label={label}
        data-testid="pitch"
        data-k={k}
      >
        <defs>
          {/* el recorte lo da la ventana visible (view) y no el campo entero: con un encuadre ajustado el césped y las líneas no invaden las bandas libres de arriba y abajo */}
          <clipPath id={`pc-${uid}`}>
            <rect x={X(Math.max(0, vx0))} y={Y(Math.min(PITCH.width, vy1))} width={S(Math.min(PITCH.length, vx1) - Math.max(0, vx0))} height={S(Math.min(PITCH.width, vy1) - Math.max(0, vy0))} rx={cropped ? 0 : 6} />
          </clipPath>
          {/* las líneas se recortan 3 px más allá de la ventana: el trazo de la línea de banda o de fondo no se corta por la mitad */}
          <clipPath id={`pl-${uid}`}>
            <rect
              x={X(Math.max(0, vx0)) - (vx0 <= 0 ? 3 + goalExt : 0)}
              y={Y(Math.min(PITCH.width, vy1)) - (vy1 >= PITCH.width ? 3 : 0)}
              width={S(Math.min(PITCH.length, vx1) - Math.max(0, vx0)) + (vx0 <= 0 ? 3 + goalExt : 0) + (vx1 >= PITCH.length ? 3 + goalExt : 0)}
              height={S(Math.min(PITCH.width, vy1) - Math.max(0, vy0)) + (vy1 >= PITCH.width ? 3 : 0) + (vy0 <= 0 ? 3 : 0)}
            />
          </clipPath>
          <radialGradient id={`pv-${uid}`} cx="50%" cy="50%" r="75%">
            <stop offset="0" stopColor="#fff" stopOpacity="0.05" />
            <stop offset="1" stopColor="#000" stopOpacity="0.28" />
          </radialGradient>
        </defs>

        {/* césped */}
        <g clipPath={`url(#pc-${uid})`} data-layer="turf">
          <rect x={X(0)} y={Y(PITCH.width)} width={S(PITCH.length)} height={S(PITCH.width)} fill="var(--c-pitch-base)" />
          {Array.from({ length: STRIPES }, (_, i) =>
            i % 2 === 0 ? (
              <rect
                key={i}
                data-stripe={i}
                x={X(i * stripeW)}
                y={Y(PITCH.width)}
                width={S(stripeW)}
                height={S(PITCH.width)}
                fill="var(--c-pitch-stripe)"
              />
            ) : null,
          )}
          <rect x={X(0)} y={Y(PITCH.width)} width={S(PITCH.length)} height={S(PITCH.width)} fill={`url(#pv-${uid})`} />
        </g>

        {/* líneas */}
        <g data-layer="lines" clipPath={cropped ? `url(#pl-${uid})` : undefined} {...line}>
          <rect
            data-line="outline"
            x={X(0)}
            y={Y(PITCH.width)}
            width={S(PITCH.length)}
            height={S(PITCH.width)}
            rx={2}
          />
          <line data-line="halfway" x1={X(PITCH.length / 2)} y1={Y(0)} x2={X(PITCH.length / 2)} y2={Y(PITCH.width)} />
          <circle data-line="center-circle" cx={X(PITCH.length / 2)} cy={Y(mid)} r={S(PITCH.centerCircleRadius)} />
          <circle
            data-line="center-spot"
            cx={X(PITCH.length / 2)}
            cy={Y(mid)}
            r={3.5}
            fill="var(--c-pitch-line)"
            stroke="none"
          />
          {sides.map((s) => (
            <g key={s.side}>
              <rect data-line={`penalty-area-${s.side}`} {...s.penalty} />
              <rect data-line={`goal-area-${s.side}`} {...s.goalArea} />
              <rect data-line={`goal-${s.side}`} {...s.goal} strokeWidth={3.5} />
              <circle
                data-line={`penalty-spot-${s.side}`}
                cx={s.spot.x}
                cy={s.spot.y}
                r={3.5}
                fill="var(--c-pitch-line)"
                stroke="none"
              />
              <path data-line={`penalty-arc-${s.side}`} d={s.arc} />
            </g>
          ))}
          {corners.map((c) => (
            <path key={c.key} data-line="corner-arc" d={c.d} />
          ))}
        </g>

        {children}
      </svg>
    </PitchContext.Provider>
  );
}
