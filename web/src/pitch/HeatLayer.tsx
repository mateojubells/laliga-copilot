import { contours } from "d3-contour";
import { interpolateRgbBasis } from "d3-interpolate";
import { useId, useMemo } from "react";
import { usePitch } from "./context";

/**
 * Rampa tipo magma: casi negro → morado → magenta → coral → crema (luminosidad creciente). No contiene verde, así que
 * ni se confunde con el césped ni la cola débil parece hierba; sobre el campo oscuro (mezcla "screen") lo frío desaparece.
 */
export const HEAT_RAMP = interpolateRgbBasis(["#000004", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"]);

/** Suavizado gaussiano separable aproximado (núcleo binomial 1-2-1), `passes` veces. */
export function smoothGrid(grid: readonly number[], cols: number, rows: number, passes = 2): number[] {
  let g = [...grid];
  const k = [0.25, 0.5, 0.25];
  for (let p = 0; p < passes; p++) {
    const h = new Array<number>(g.length).fill(0);
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++) {
        let s = 0;
        for (let d = -1; d <= 1; d++) s += (g[r * cols + Math.min(cols - 1, Math.max(0, c + d))] ?? 0) * k[d + 1]!;
        h[r * cols + c] = s;
      }
    const v = new Array<number>(g.length).fill(0);
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++) {
        let s = 0;
        for (let d = -1; d <= 1; d++) s += (h[Math.min(rows - 1, Math.max(0, r + d)) * cols + c] ?? 0) * k[d + 1]!;
        v[r * cols + c] = s;
      }
    g = v;
  }
  return g;
}

type Ring = number[][];
function ringsToPath(coords: Ring[][], tx: (gx: number) => number, ty: (gy: number) => number): string {
  let d = "";
  for (const poly of coords)
    for (const ring of poly) {
      ring.forEach((p, i) => {
        d += `${i === 0 ? "M" : "L"}${tx(p[0]!).toFixed(1)} ${ty(p[1]!).toFixed(1)} `;
      });
      d += "Z ";
    }
  return d;
}

const LEVELS = [0.1, 0.2, 0.32, 0.45, 0.58, 0.7, 0.82, 0.92];

/**
 * Mapa de calor: rejilla cols×rows (filas desde y=0, es decir desde ABAJO) → suavizado → isobandas con d3-contour.
 * Se rellena el borde replicando la última fila/columna para que el calor no se desvanezca contra la línea de banda.
 */
export function HeatLayer({ grid, cols, rows }: { grid: readonly number[]; cols: number; rows: number }) {
  const { x, y } = usePitch();
  const uid = useId().replace(/:/g, "");
  const shapes = useMemo(() => {
    const PAD = 2;
    const W = cols + 2 * PAD;
    const H = rows + 2 * PAD;
    const sm = smoothGrid(grid, cols, rows, 2);
    const max = Math.max(1e-9, ...sm);
    // contours() espera fila 0 = ARRIBA: invertimos (el dato viene con fila 0 = y=0 abajo)
    const padded = new Array<number>(W * H);
    for (let r = 0; r < H; r++)
      for (let c = 0; c < W; c++) {
        const srcR = Math.min(rows - 1, Math.max(0, rows - 1 - (r - PAD))); // fila de pantalla → fila de datos
        const srcC = Math.min(cols - 1, Math.max(0, c - PAD));
        padded[r * W + c] = (sm[srcR * cols + srcC] ?? 0) / max;
      }
    const gen = contours().size([W, H]).smooth(true).thresholds(LEVELS);
    return gen(padded).map((c, i) => ({ value: LEVELS[i]!, coords: c.coordinates as unknown as Ring[][] }));
  }, [grid, cols, rows]);

  const x0 = x(0);
  const y0 = y(68);
  const cw = (x(105) - x(0)) / cols;
  const ch = (y(0) - y(68)) / rows;
  const tx = (gx: number) => x0 + (gx - 2) * cw;
  const ty = (gy: number) => y0 + (gy - 2) * ch;

  return (
    <g data-layer="heat">
      <defs>
        <clipPath id={`hc-${uid}`}>
          <rect x={x0} y={y0} width={x(105) - x0} height={y(0) - y0} rx={6} />
        </clipPath>
        <filter id={`hb-${uid}`} x="-5%" y="-5%" width="110%" height="110%">
          <feGaussianBlur stdDeviation="7" />
        </filter>
      </defs>
      <g clipPath={`url(#hc-${uid})`} filter={`url(#hb-${uid})`} style={{ mixBlendMode: "screen" }}>
        {shapes.map((s) => (
          <path
            key={s.value}
            data-heat-level={s.value}
            d={ringsToPath(s.coords, tx, ty)}
            fill={HEAT_RAMP(s.value)}
            fillOpacity={0.35 + 0.35 * s.value}
            fillRule="evenodd"
          />
        ))}
      </g>
    </g>
  );
}

/** Líneas de tercios (x = 35 y 70 m) en discontinua fina: respaldan cifras como "último tercio 58 %". */
export function ThirdsLines() {
  const { x, y } = usePitch();
  return (
    <g data-layer="thirds" stroke="#fff" strokeOpacity={0.35} strokeWidth={2} strokeDasharray="8 8">
      {[35, 70].map((m) => (
        <line key={m} x1={x(m)} y1={y(0)} x2={x(m)} y2={y(68)} />
      ))}
    </g>
  );
}

/** Reparto de la rejilla por tercios del campo (defensivo, medio, ataque), en % que suman 100. */
export function thirdsShare(grid: readonly number[], cols: number, rows: number): [number, number, number] {
  const sum = [0, 0, 0];
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) sum[Math.min(2, Math.floor(((c + 0.5) / cols) * 3))]! += grid[r * cols + c] ?? 0;
  const total = sum[0]! + sum[1]! + sum[2]!;
  if (total <= 0) return [0, 0, 0];
  const pct = sum.map((v) => Math.floor((v / total) * 100));
  // el resto del redondeo va al tercio mayor para que sume exactamente 100
  const big = pct.indexOf(Math.max(...pct));
  pct[big]! += 100 - pct.reduce((a, b) => a + b, 0);
  return pct as [number, number, number];
}
