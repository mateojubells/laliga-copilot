import { scaleLinear } from "d3-scale";
import { motion } from "framer-motion";
import type { Arrow } from "../contracts";
import { drawVariants, headVariants } from "../design/motion";
import { usePitch } from "./context";

/** Flecha para el campo: el contrato `Arrow` + recuento opcional (grosor) + holguras en px (para no pisar nodos). */
export interface ArrowDatum extends Pick<Arrow, "x" | "y" | "end_x" | "end_y"> {
  kind?: Arrow["kind"];
  count?: number;
  highlight?: boolean;
  /** Grosor fijo en px (si no hay `count`; p. ej. pase 5, pase clave 7, asistencia 9). */
  width?: number;
  /** Opacidad propia (0-1); si falta se usa la de la capa. La red de pases la liga al recuento. */
  opacity?: number;
  /** px de holgura al inicio y al final (radio de los nodos). */
  gapStart?: number;
  gapEnd?: number;
  /** Desplazamiento perpendicular (px) para separar los pares de ida y vuelta. */
  offset?: number;
  /** Sin punta (líneas bidireccionales y flechas menores de la red de pases). */
  noHead?: boolean;
}

/**
 * PALETA ÚNICA de flechas de los cuatro grafismos de campo (y de sus leyendas, que dibujan exactamente estos trazos):
 * pase = blanco al 45 %, pase clave = blanco pleno, asistencia = dorado, destacada = color del club con contorno blanco.
 */
export const ARROW_STYLE: Record<NonNullable<Arrow["kind"]>, { color: string; opacity: number; width: number }> = {
  pass: { color: "#ffffff", opacity: 0.45, width: 3 },
  cross: { color: "#ffffff", opacity: 0.45, width: 3 },
  carry: { color: "#ffffff", opacity: 0.45, width: 3 },
  key_pass: { color: "#ffffff", opacity: 1, width: 4 },
  assist: { color: "#ffd23f", opacity: 1, width: 5 },
};
/** Opacidad de las flechas con grosor ∝ recuento (red de pases): el grosor cuenta los pases, la opacidad es fija. */
export const ARROW_COUNT_OPACITY = 0.55;
/** Color del trazo y del aro de la flecha destacada. */
export const ARROW_HL_OUTLINE = "#ffffff";

/** Rango de grosor (px) de las flechas con recuento. */
export const ARROW_W_MIN = 4;
export const ARROW_W_MAX = 18;

/**
 * Grosor (px) de una flecha según su recuento: lineal entre el UMBRAL (el mínimo que se pinta, p. ej. 10 pases) y el
 * máximo del conjunto, de 4 a 18 px. Con umbral 10 y máximo 26: 10 → 4, 18 → 11, 26 → 18 px: se distinguen.
 * Compartido con las leyendas.
 */
export function arrowWidth(count: number, max: number, min = 1): number {
  const hi = Math.max(max, min + 1);
  return scaleLinear().domain([min, hi]).range([ARROW_W_MIN, ARROW_W_MAX]).clamp(true)(count);
}

const KIND_RANK: Record<NonNullable<Arrow["kind"]>, number> = { carry: 0, pass: 1, cross: 1, key_pass: 2, assist: 3 };

export interface ArrowGeom {
  path: string;
  head: string;
  width: number;
}

/** Geometría de una flecha curva (Bézier cuadrática) con punta triangular, todo en píxeles. */
export function arrowGeometry(
  a: { x: number; y: number },
  b: { x: number; y: number },
  width: number,
  gapStart = 0,
  gapEnd = 0,
  bend = 0.08,
  offset = 0,
  noHead = false,
): ArrowGeom {
  const dx0 = b.x - a.x;
  const dy0 = b.y - a.y;
  const len = Math.hypot(dx0, dy0) || 1;
  const ux = dx0 / len;
  const uy = dy0 / len;
  // desplazamiento perpendicular (a la derecha del sentido de la flecha): a→b y b→a quedan en carriles distintos
  if (offset) {
    a = { x: a.x - uy * offset, y: a.y + ux * offset };
    b = { x: b.x - uy * offset, y: b.y + ux * offset };
  }
  // curvatura: control desplazado en perpendicular; a→b y b→a se curvan hacia lados opuestos
  const cx = (a.x + b.x) / 2 - uy * len * bend;
  const cy = (a.y + b.y) / 2 + ux * len * bend;
  const s = { x: a.x + ux * gapStart, y: a.y + uy * gapStart };
  const tip = { x: b.x - ux * gapEnd, y: b.y - uy * gapEnd };
  // dirección de llegada = tangente final de la curva
  const tx = tip.x - cx;
  const ty = tip.y - cy;
  const tl = Math.hypot(tx, ty) || 1;
  const tux = tx / tl;
  const tuy = ty / tl;
  const headLen = noHead ? 0 : Math.max(14, width * 2.4);
  const headHalf = Math.max(7, width * 1.3);
  const base = { x: tip.x - tux * headLen, y: tip.y - tuy * headLen };
  const px = -tuy;
  const py = tux;
  const head = `${tip.x},${tip.y} ${base.x + px * headHalf},${base.y + py * headHalf} ${base.x - px * headHalf},${base.y - py * headHalf}`;
  return { path: `M ${s.x} ${s.y} Q ${cx} ${cy} ${base.x} ${base.y}`, head, width };
}

/** Flechas de pase: curvas suaves con punta, grosor ∝ recuento. Se dibujan (pathLength) al entrar el grafismo. */
export function ArrowsLayer({
  arrows,
  color,
  opacity,
  minCount,
  endDots = false,
  highlightColor,
}: {
  arrows: readonly ArrowDatum[];
  color?: string;
  /** Opacidad de las flechas que no la traen propia (por defecto, la de su tipo en ARROW_STYLE). */
  opacity?: number;
  /** Color de la flecha destacada (por defecto, el acento); siempre con contorno blanco. */
  highlightColor?: string;
  /** Umbral del dominio de grosor (por defecto, el menor recuento presente). */
  minCount?: number;
  /** Los pases simples terminan en un punto de 8 px (sin punta): menos ruido; pase clave y asistencia llevan punta. */
  endDots?: boolean;
}) {
  const { x, y, accent } = usePitch();
  const counts = arrows.flatMap((a) => (a.count != null ? [a.count] : []));
  const max = Math.max(1, ...counts);
  const lo = minCount ?? Math.min(max, ...counts);
  // lo más importante, encima: pase < pase clave < asistencia < destacado
  const rank = (a: ArrowDatum) => (a.highlight ? 10 : KIND_RANK[a.kind ?? "pass"]);
  const ordered = [...arrows].sort((a, b) => rank(a) - rank(b));
  return (
    <g data-layer="arrows" strokeLinecap="round" strokeLinejoin="round">
      {ordered.map((a, i) => {
        const kind = a.kind ?? "pass";
        const st = ARROW_STYLE[kind];
        const width = a.count != null ? arrowWidth(a.count, max, lo) : (a.width ?? st.width);
        const g = arrowGeometry({ x: x(a.x), y: y(a.y) }, { x: x(a.end_x), y: y(a.end_y) }, width, a.gapStart, a.gapEnd, undefined, a.offset, a.noHead);
        const c = a.highlight ? (highlightColor ?? accent) : (color ?? st.color);
        const op = a.highlight ? 1 : (a.opacity ?? opacity ?? st.opacity);
        const plain = !a.highlight && kind !== "key_pass" && kind !== "assist";
        const dot = endDots && plain && !a.noHead;
        const tip = g.head.split(" ")[0]!.split(",").map(Number);
        const under = a.highlight ? ARROW_HL_OUTLINE : "rgba(0,0,0,0.45)";
        const underW = a.highlight ? g.width + 6 : g.width + 3;
        return (
          <g key={i} data-arrow={kind} data-highlight={a.highlight ? "true" : undefined} opacity={op} color={c}>
            <motion.path d={g.path} fill="none" stroke={under} strokeWidth={underW} variants={drawVariants} custom={i} />
            <motion.path d={g.path} fill="none" stroke={c} strokeWidth={g.width} variants={drawVariants} custom={i} />
            {a.noHead ? null : dot ? (
              <motion.circle cx={tip[0]} cy={tip[1]} r={4} fill="#fff" stroke="rgba(0,0,0,0.45)" strokeWidth={1.5} variants={headVariants} custom={i} />
            ) : (
              <motion.polygon points={g.head} fill={c} stroke={a.highlight ? ARROW_HL_OUTLINE : "rgba(0,0,0,0.45)"} strokeWidth={a.highlight ? 3 : 1.5} variants={headVariants} custom={i} />
            )}
          </g>
        );
      })}
    </g>
  );
}
