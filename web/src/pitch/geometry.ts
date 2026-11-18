/** Medidas reglamentarias del campo (metros). Fuente: Reglas de Juego IFAB, campo 105×68. */
export const PITCH = {
  length: 105,
  width: 68,
  penaltyArea: { depth: 16.5, width: 40.32 },
  goalArea: { depth: 5.5, width: 18.32 },
  penaltySpot: 11,
  centerCircleRadius: 9.15,
  penaltyArcRadius: 9.15,
  cornerRadius: 1,
  goal: { width: 7.32, depth: 2.44 },
} as const;

export interface Pt {
  x: number;
  y: number;
}

/** Arco SVG de radio r centrado en c, de s a e (arco corto), calculando el sentido con el producto vectorial. */
export function arcPath(c: Pt, s: Pt, e: Pt, r: number): string {
  const cross = (s.x - c.x) * (e.y - c.y) - (s.y - c.y) * (e.x - c.x);
  const sweep = cross > 0 ? 1 : 0; // en coordenadas SVG (y hacia abajo) cross>0 = sentido horario
  return `M ${s.x} ${s.y} A ${r} ${r} 0 0 ${sweep} ${e.x} ${e.y}`;
}

/** y (m) de los extremos de un rectángulo centrado en la línea media de portería. */
export function centeredSpan(width: number): [number, number] {
  const mid = PITCH.width / 2;
  return [mid - width / 2, mid + width / 2];
}

/** Medida del punto donde el arco del área corta la línea del área grande: dy desde el eje. */
export function penaltyArcHalfChord(): number {
  const dx = PITCH.penaltyArea.depth - PITCH.penaltySpot;
  return Math.sqrt(PITCH.penaltyArcRadius ** 2 - dx ** 2);
}

export interface ViewBox {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

/**
 * Encuadre del campo a la zona donde ocurre la acción (en metros): caja de los puntos + `margin`, recortada al campo, con una
 * escala mínima de `minK` px/m (si la zona es más ancha, se recorta lo más alejado: con `anchor: "right"` se conserva el
 * lado de la portería rival) y un alto de dibujo entre `minPlotH` y `maxPlotH` px (se amplía o se recorta en vertical).
 * `width` es el ancho del viewBox y `padding` el margen que el campo deja en los lados donde TERMINA de verdad.
 */
export function fitView(
  points: readonly (readonly [number, number])[],
  o: { width: number; padding: number; margin?: number; minK?: number; maxK?: number; minPlotH?: number; maxPlotH?: number; anchor?: "center" | "right"; fallback: ViewBox },
): ViewBox {
  const { width, padding, margin = 6, minK = 9, maxK = 13, minPlotH = 0, maxPlotH = Infinity, anchor = "center" } = o;
  const L = PITCH.length;
  const W = PITCH.width;
  const pts = points.filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  let { x0, x1, y0, y1 } = o.fallback;
  if (pts.length > 0) {
    x0 = Math.max(0, Math.min(...pts.map((p) => p[0])) - margin);
    x1 = Math.min(L, Math.max(...pts.map((p) => p[0])) + margin);
    y0 = Math.max(0, Math.min(...pts.map((p) => p[1])) - margin);
    y1 = Math.min(W, Math.max(...pts.map((p) => p[1])) + margin);
  }
  // ya casi en la línea de banda: se llega hasta ella (queda dibujada y el encuadre no deja una franja de césped sin línea)
  const SNAP = 6;
  if (y0 <= SNAP) y0 = 0;
  if (y1 >= W - SNAP) y1 = W;
  const plotW = () => width - (x0 <= 0 ? padding : 0) - (x1 >= L ? padding : 0);
  // escala mínima: se recorta en horizontal
  const maxSpanX = plotW() / minK;
  if (x1 - x0 > maxSpanX) {
    if (anchor === "right") x0 = x1 - maxSpanX;
    else {
      const mid = (x0 + x1) / 2;
      x0 = Math.max(0, mid - maxSpanX / 2);
      x1 = Math.min(L, x0 + maxSpanX);
      x0 = Math.max(0, x1 - maxSpanX);
    }
  }
  // tampoco demasiado cerca: con dos jugadores casi juntos la escala se dispara y los nodos (∝ k) taparían el campo
  const minSpanX = plotW() / maxK;
  if (x1 - x0 < minSpanX) {
    const mid = (x0 + x1) / 2;
    x0 = Math.max(0, Math.min(mid - minSpanX / 2, L - minSpanX));
    x1 = Math.min(L, x0 + minSpanX);
  }
  const k = plotW() / (x1 - x0);
  // alto: entre minPlotH y maxPlotH (px) → metros
  const fit = (lo: number, hi: number, target: number): [number, number] => {
    const mid = (lo + hi) / 2;
    let a = mid - target / 2;
    let b = mid + target / 2;
    if (a < 0) { b = Math.min(W, b - a); a = 0; }
    if (b > W) { a = Math.max(0, a - (b - W)); b = W; }
    return [a, b];
  };
  const span = y1 - y0;
  if (span * k < minPlotH) [y0, y1] = fit(y0, y1, minPlotH / k);
  else if (span * k > maxPlotH) [y0, y1] = fit(y0, y1, maxPlotH / k);
  return { x0, x1, y0, y1 };
}
