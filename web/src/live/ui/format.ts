export function fmtClock(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${String(m).padStart(2, "0")}:${ss}`;
}

export const EVENT_LABEL: Record<string, string> = {
  gol: "Gol", tiro: "Tiro", parada: "Parada", palo: "Palo", ocasion: "Ocasión", pase: "Pase", centro: "Centro",
  asistencia: "Asistencia", regate: "Regate", falta: "Falta", penalti: "Penalti", mano: "Mano", corner: "Córner",
  saque_banda: "Saque de banda", saque_puerta: "Saque de puerta", fuera_juego: "Fuera de juego", amarilla: "Amarilla",
  roja: "Roja", cambio: "Cambio", lesion: "Lesión", robo: "Robo", perdida: "Pérdida", despeje: "Despeje", var: "VAR",
  inicio: "Inicio", descanso: "Descanso", final: "Final",
};
export const EVENT_TYPES = Object.keys(EVENT_LABEL);

export const PERIOD = ["Previa", "1.ª parte", "2.ª parte", "Final"];
