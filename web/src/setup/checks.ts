export type CheckStatus = "ok" | "warn" | "bad" | "pending";

export interface Check {
  id: string;
  label: string;
  status: CheckStatus;
  detail: string;
  /** Si es true y no está "ok", "Empezar partido" queda desactivado. */
  blocking: boolean;
}

export interface CheckInput {
  serverOk: boolean | null; // null = aún no se sabe
  serverError?: string;
  seasonHasResults: boolean | null;
  matchChosen: boolean;
  lineupErrors: string[]; // vacío = válidas (o aún sin cargar si lineupsLoaded=false)
  lineupsLoaded: boolean;
  voice: "mic" | "replay" | "none";
  micPeak: number | null; // pico máximo de la última prueba; null = sin probar
  micTooQuiet: boolean;
  programClients: number | null; // null = sin dato
}

export function buildChecks(i: CheckInput): Check[] {
  const out: Check[] = [];
  out.push(i.serverOk == null
    ? { id: "server", label: "El servidor responde", status: "pending", detail: "Comprobando…", blocking: true }
    : { id: "server", label: "El servidor responde", status: i.serverOk ? "ok" : "bad", detail: i.serverOk ? "Conectado" : i.serverError ?? "Sin respuesta", blocking: true });
  out.push(!i.matchChosen
    ? { id: "season", label: "Temporada con datos", status: "pending", detail: "Elige un partido", blocking: true }
    : { id: "season", label: "Temporada con datos", status: i.seasonHasResults ? "ok" : "warn", detail: i.seasonHasResults ? "Resultados reales disponibles" : "Sin resultados reales: sólo plantillas", blocking: false });
  out.push(!i.lineupsLoaded
    ? { id: "lineups", label: "Alineaciones válidas", status: "pending", detail: i.matchChosen ? "Cargando…" : "Elige un partido", blocking: true }
    : i.lineupErrors.length
      ? { id: "lineups", label: "Alineaciones válidas", status: "bad", detail: i.lineupErrors[0], blocking: true }
      : { id: "lineups", label: "Alineaciones válidas", status: "ok", detail: "11 titulares y portero en los dos equipos", blocking: true });
  if (i.voice === "mic") {
    out.push(i.micPeak == null
      ? { id: "mic", label: "Micrófono con señal", status: "warn", detail: "Sin probar: usa «Probar 5 s» en el paso 4", blocking: false }
      : i.micTooQuiet
        ? { id: "mic", label: "Micrófono con señal", status: "warn", detail: "La señal es muy baja; sube la ganancia o acércate", blocking: false }
        : { id: "mic", label: "Micrófono con señal", status: "ok", detail: "Nivel correcto", blocking: false });
  }
  out.push(i.programClients == null
    ? { id: "program", label: "Salida de programa conectada", status: "warn", detail: "Sin dato todavía (aviso, no bloquea)", blocking: false }
    : i.programClients > 0
      ? { id: "program", label: "Salida de programa conectada", status: "ok", detail: `${i.programClients} página(s) /program`, blocking: false }
      : { id: "program", label: "Salida de programa conectada", status: "warn", detail: "Abre /program (aviso, no bloquea)", blocking: false });
  return out;
}

export const canStart = (checks: Check[]) => checks.every((c) => !c.blocking || c.status === "ok");
