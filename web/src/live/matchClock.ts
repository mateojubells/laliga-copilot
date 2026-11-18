import type { MatchState } from "../contracts";

/**
 * Reloj del partido en el cliente.
 * El servidor manda (clock_running, clock_base_s, clock_at_ms) en su propio reloj monotónico (ms). El cliente conoce el
 * desfase con ClockSync (serverNow = performance.now() + offset), así que el segundo del partido en cualquier instante es
 *   base + (serverNow − clock_at_ms) / 1000          si corre
 *   base                                              si está parado
 * clock_base_s son segundos de partido absolutos (45:00 = 2700, 90:00 = 5400).
 */
export function clockSeconds(m: MatchState | null | undefined, serverNowMs: number | null): number {
  if (!m) return 0;
  const base = Math.max(0, m.clock_base_s ?? 0);
  if (!m.clock_running || m.clock_at_ms == null || serverNowMs == null) return base;
  return base + Math.max(0, (serverNowMs - m.clock_at_ms) / 1000);
}

/** mm:ss (los minutos pasan de 59 sin convertir a horas: 95:03). */
export function fmtMatchClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export type Phase = "pre" | "first" | "half" | "second" | "final";

export const PHASE_LABEL: Record<Phase, string> = {
  pre: "Previa", first: "1.ª parte", half: "Descanso", second: "2.ª parte", final: "Final",
};

const HALF_S = 2700;

/**
 * Fase visible. El modelo sólo tiene period 0..3; el descanso se reconoce porque el reloj está parado tras haber
 * empezado: period 1 parado con base > 0, o period 2 parado en o antes de 45:00 (aún no ha empezado la 2.ª).
 */
export function phaseOf(m: MatchState | null | undefined): Phase {
  const p = m?.period ?? 0;
  if (p === 0) return "pre";
  if (p === 3) return "final";
  const running = !!m?.clock_running;
  const base = m?.clock_base_s ?? 0;
  if (p === 1) return !running && base > 0 ? "half" : "first";
  return !running && base <= HALF_S + 0.5 ? "half" : "second";
}

export interface PeriodControl {
  label: string;
  value: "kickoff" | "half_time" | "second_half" | "full_time";
  /** Pide confirmación en la propia interfaz antes de enviar. */
  confirm: boolean;
}

/** Botón contextual único: qué acción de reloj toca ahora. null si el partido ya terminó. */
export function periodControl(m: MatchState | null | undefined): PeriodControl | null {
  switch (phaseOf(m)) {
    case "pre": return { label: "Pitido inicial", value: "kickoff", confirm: false };
    case "first": return { label: "Descanso", value: "half_time", confirm: false };
    case "half": return { label: "Inicio 2.ª parte", value: "second_half", confirm: false };
    case "second": return { label: "Final", value: "full_time", confirm: true };
    case "final": return null;
  }
}
