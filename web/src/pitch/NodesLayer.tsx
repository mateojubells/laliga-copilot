import { scaleSqrt } from "d3-scale";
import { motion } from "framer-motion";
import { popVariants } from "../design/motion";
import { usePitch } from "./context";
import type { ArrowDatum } from "./ArrowsLayer";

export interface NodeDatum {
  id: string;
  x: number;
  y: number;
  number?: number | null;
  label: string;
  /** Magnitud que da el tamaño (pases). */
  size: number;
  fill: string;
  textColor: string;
  stroke?: string;
  highlight?: boolean;
  /** Posición media del receptor: silueta al 50 % (las flechas acaban en los puntos reales de recepción). */
  ghost?: boolean;
}

/** Mínimos de legibilidad: dorsal de 30 px, nombre de 26 px, radio de 26 px. */
export const NODE_NUMBER_MIN = 30;
export const NODE_LABEL = 26;
export const NODE_R_MIN = 26;

/** Radio (px) del nodo dados el dominio de tamaños y los píxeles por metro. */
export function nodeRadiusScale(sizes: readonly number[], k: number) {
  const max = Math.max(1, ...sizes);
  const min = Math.min(max - 1, ...sizes);
  const f = k / 10;
  return scaleSqrt()
    .domain([Math.max(0, Math.min(min, max - 1)), max])
    .range([Math.max(NODE_R_MIN, 32 * f), Math.max(NODE_R_MIN + 12, 48 * f)])
    .clamp(true);
}

interface Rect { x: number; y: number; w: number; h: number }

const overlap = (a: Rect, b: Rect) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const circleHits = (r: Rect, cx: number, cy: number, R: number) => {
  const nx = Math.max(r.x, Math.min(cx, r.x + r.w));
  const ny = Math.max(r.y, Math.min(cy, r.y + r.h));
  return Math.hypot(nx - cx, ny - cy) < R;
};

/** Ancho estimado (px) de la placa de una etiqueta: Inter 600 ≈ 0,56 em por carácter + 8 px de relleno a cada lado. */
export const labelPlateWidth = (text: string, size: number) => Math.round(text.length * size * 0.56 + 16);
/** Alto de la placa: texto + 2 px de relleno arriba y abajo. */
export const labelPlateHeight = (size: number) => Math.round(size * 1.2) + 4;

/**
 * Jugadores como nodos con dorsal y nombre; tamaño ∝ pases. El nombre va en una placa oscura (nunca con la opacidad del
 * nodo) colocada donde haya sitio: debajo, encima o a un lado del nodo según lo que pisaría (flechas de `avoid`, otros
 * nodos y placas, las líneas de banda y los bordes del dibujo). Aparecen escalonados (pop).
 */
export function NodesLayer({
  nodes,
  labelSize = NODE_LABEL,
  avoid = [],
}: {
  nodes: readonly NodeDatum[];
  labelSize?: number;
  /** Flechas dibujadas en el mismo campo: sus trazos puntúan en contra de una colocación. */
  avoid?: readonly Pick<ArrowDatum, "x" | "y" | "end_x" | "end_y">[];
}) {
  const { x, y, k, width, height } = usePitch();
  const r = nodeRadiusScale(nodes.map((n) => n.size), k);
  const circles = nodes.map((n) => ({ cx: x(n.x), cy: y(n.y), R: r(n.size) + (n.highlight ? 9 : 2) }));
  // trazos de las flechas muestreados cada ~10 px (basta la cuerda: la curvatura es pequeña)
  const samples: [number, number][] = avoid.flatMap((a) => {
    const x0 = x(a.x);
    const y0 = y(a.y);
    const dx = x(a.end_x) - x0;
    const dy = y(a.end_y) - y0;
    const n = Math.max(2, Math.round(Math.hypot(dx, dy) / 10));
    return Array.from({ length: n + 1 }, (_, t) => [x0 + (dx * t) / n, y0 + (dy * t) / n] as [number, number]);
  });
  const turf = { x0: x(0), x1: x(105), yTop: y(68), yBot: y(0) };
  const placed: Rect[] = [];
  const plates = nodes.map((n, i) => {
    const { cx, cy, R } = circles[i]!;
    const w = labelPlateWidth(n.label, labelSize);
    const h = labelPlateHeight(labelSize);
    const base = R + 4; // R ya incluye el aro de la destacada
    const cands: { rect: Rect; bias: number }[] = [
      { rect: { x: cx - w / 2, y: cy + base, w, h }, bias: 0 },
      { rect: { x: cx - w / 2, y: cy - base - h, w, h }, bias: 0.4 },
      { rect: { x: cx + base + 4, y: cy - h / 2, w, h }, bias: 1.2 },
      { rect: { x: cx - base - 4 - w, y: cy - h / 2, w, h }, bias: 1.2 },
    ];
    const scored = cands.map(({ rect, bias }) => {
      // dentro del dibujo: se desplaza en horizontal hasta que quepa
      const rx = Math.max(2, Math.min(width - 2 - rect.w, rect.x));
      const rc = { ...rect, x: rx };
      let score = bias + Math.abs(rx - rect.x) * 0.05;
      if (rc.y < 2 || rc.y + rc.h > height - 2) score += 30;
      // flechas
      const box = { x: rc.x - 3, y: rc.y - 3, w: rc.w + 6, h: rc.h + 6 };
      for (const [sx, sy] of samples) if (sx >= box.x && sx <= box.x + box.w && sy >= box.y && sy <= box.y + box.h) score += 1;
      // otros nodos y placas ya colocadas
      circles.forEach((c, j) => {
        if (j !== i && circleHits(rc, c.cx, c.cy, c.R + 2)) score += 40;
      });
      if (circleHits(rc, cx, cy, circles[i]!.R)) score += 40;
      for (const p of placed) if (overlap(rc, p)) score += 40;
      // líneas de banda y de fondo del césped (cruzarlas ensucia la placa; salirse del todo es peor)
      const crossesH = (ly: number) => rc.y < ly && rc.y + rc.h > ly && rc.x < turf.x1 && rc.x + rc.w > turf.x0;
      if (crossesH(turf.yTop) || crossesH(turf.yBot)) score += 6;
      if (rc.y >= turf.yBot || rc.y + rc.h <= turf.yTop) score += 4;
      return { rc, score };
    });
    scored.sort((a, b) => a.score - b.score);
    const best = scored[0]!.rc;
    placed.push(best);
    return best;
  });
  return (
    <g data-layer="nodes">
      {nodes.map((n, i) => {
        const { cx, cy } = circles[i]!;
        const R = r(n.size);
        const plate = plates[i]!;
        return (
          <motion.g key={n.id} data-node={n.id} data-r={R.toFixed(1)} variants={popVariants} custom={i}>
            <g opacity={n.ghost ? 0.55 : 1}>
              {n.highlight && <circle cx={cx} cy={cy} r={R + 9} fill="none" stroke="#fff" strokeWidth={4} />}
              <circle cx={cx} cy={cy} r={R + 1.5} fill="rgba(4,8,14,0.55)" />
              <circle cx={cx} cy={cy} r={R} fill={n.fill} stroke={n.stroke ?? "#fff"} strokeWidth={3.5} />
              {n.number != null && (
                <text
                  x={cx}
                  y={cy}
                  dy="0.36em"
                  textAnchor="middle"
                  fontFamily="var(--font-display)"
                  fontWeight={800}
                  fontSize={Math.round(Math.max(NODE_NUMBER_MIN, R * 0.95))}
                  fill={n.textColor}
                >
                  {n.number}
                </text>
              )}
            </g>
            <g data-label={n.id}>
              <rect x={plate.x} y={plate.y} width={plate.w} height={plate.h} rx={6} fill="rgba(5,8,14,0.72)" />
              <text
                x={plate.x + plate.w / 2}
                y={plate.y + plate.h / 2}
                dy="0.35em"
                textAnchor="middle"
                fontFamily="var(--font-text)"
                fontWeight={600}
                fontSize={labelSize}
                fill="#fff"
              >
                {n.label}
              </text>
            </g>
          </motion.g>
        );
      })}
    </g>
  );
}
