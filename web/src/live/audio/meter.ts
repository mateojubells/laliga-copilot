/** Pico (0..1) de un bloque de muestras float. */
export function peakOf(buf: ArrayLike<number>): number {
  let p = 0;
  for (let i = 0; i < buf.length; i++) {
    const a = Math.abs(buf[i]);
    if (a > p) p = a;
  }
  return p;
}

/** Pico → posición del medidor (0..1) en escala dB de −60 a 0 (el oído no es lineal). */
export function levelToMeter(peak: number): number {
  if (!(peak > 0)) return 0;
  const db = 20 * Math.log10(Math.min(1, peak));
  return Math.max(0, Math.min(1, (db + 60) / 60));
}

/** Por debajo de este pico (≈ −34 dBFS) la voz llega demasiado baja para el motor de reconocimiento. */
export const LOW_PEAK = 0.02;
export const isTooQuiet = (peak: number) => peak < LOW_PEAK;
