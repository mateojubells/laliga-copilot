import { hsl, rgb } from "d3-color";
import { interpolateRgb } from "d3-interpolate";

/** Luminancia relativa WCAG de un color CSS (hex o rgb()). */
export function luminance(color: string): number {
  const c = rgb(color);
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
}

/** Ratio de contraste WCAG entre dos colores (1-21). */
export function contrast(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Fondo de referencia de los paneles (glass oscuro) para calcular contrastes. */
export const GLASS_REF = "#0b1018";

/**
 * Acento legible para TRAZOS y barras (líneas del campo, aros, relleno de barras) y, como mucho, cifras de 56 px o más.
 * Para objetos gráficos y texto grande basta un contraste de 3:1 (WCAG 1.4.11 / 1.4.3): se aclara solo lo justo, en HSL,
 * conservando tono Y saturación del club (sin forzarla: forzarla llevaba el granate del Barça a un magenta chicle).
 * NO es el color del club para rellenos: tiles, bandas, filetes y cabeceras usan el color oficial sin tocar (`--club-fill`).
 * Las cifras grandes van en blanco, con el color del club en un bloque o filete a su lado. Los casi grises se mezclan hacia
 * el blanco.
 */
export function accentOn(color: string, bg: string = GLASS_REF, min = 3): string {
  if (contrast(color, bg) >= min) return rgb(color).formatHex();
  const h = hsl(color);
  if (!Number.isNaN(h.h) && h.s >= 0.25) {
    for (let l = h.l; l <= 0.9; l += 0.01) {
      const c = hsl(h.h, h.s, l).formatHex();
      if (contrast(c, bg) >= min) return c;
    }
  }
  const toWhite = interpolateRgb(color, "#ffffff");
  for (let t = 0.05; t <= 1; t += 0.05) {
    const c = toWhite(t);
    if (contrast(c, bg) >= min) return rgb(c).formatHex();
  }
  return "#ffffff";
}

/**
 * Color del club para FILETES, franjas y barras finas sobre el cristal oscuro: el oficial, salvo que casi se confunda con el
 * fondo (un azul marino de 1,2:1 desaparece): entonces se aclara solo hasta 1,8:1 (el granate del Barça y el violeta del
 * Valladolid, a 2:1 o más, no se tocan). Los BLOQUES (tiles, píldoras, bloque del título) siguen con el color oficial.
 */
export const edgeOn = (color: string): string => accentOn(color, GLASS_REF, 1.8);

/** Texto (blanco o casi negro) con mejor contraste sobre un fondo dado. */
export function inkOn(bg: string, light = "#ffffff", dark = "#06090f"): string {
  return contrast(light, bg) >= contrast(dark, bg) ? light : dark;
}

/** Mezcla `color` con `into` en la proporción t (0-1). */
export function mix(color: string, into: string, t: number): string {
  return rgb(interpolateRgb(color, into)(t)).formatHex();
}

const dist = (a: string, b: string) => {
  const x = rgb(a);
  const y = rgb(b);
  return Math.hypot(x.r - y.r, x.g - y.g, x.b - y.b);
};

/**
 * Dos acentos legibles y distinguibles para enfrentar A y B (comparativas, línea de tiempo, balance del cara a cara).
 * Si los colores principales se parecen (dos jugadores del mismo club) B pasa a su secundario, luego al secundario de A.
 */
export function pairAccents(
  a: { primary?: string; secondary?: string },
  b: { primary?: string; secondary?: string },
  minDistance = 110,
): [string, string] {
  const ca = accentOn(a.primary ?? "#7cc4ff");
  const first = accentOn(b.primary ?? "#ffc247");
  if (dist(ca, first) >= minDistance) return [ca, first];
  for (const alt of [b.secondary, a.secondary]) {
    if (!alt) continue;
    const c = accentOn(alt);
    if (dist(ca, c) >= minDistance) return [ca, c];
  }
  return [ca, dist(ca, "#ffc247") >= minDistance ? "#ffc247" : "#7cc4ff"];
}
