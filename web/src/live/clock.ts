/**
 * Sincronía de relojes cliente↔servidor (NTP simplificado).
 * El cliente manda ping con client_now (performance.now()); el servidor contesta hello con ese client_now y su server_now
 * (time.monotonic()*1000). Suponiendo trayecto simétrico: offset = server_now − (client_now + rtt/2).
 */
export interface ClockSample {
  rtt: number;
  offset: number;
}

export function estimateOffset(clientSent: number, serverNow: number, clientRecv: number): ClockSample {
  const rtt = clientRecv - clientSent;
  return { rtt, offset: serverNow - (clientSent + rtt / 2) };
}

/** Guarda las últimas muestras y se queda con la de menor RTT (la menos contaminada por colas de red). */
export class ClockSync {
  private samples: ClockSample[] = [];
  constructor(private readonly keep = 8) {}

  add(clientSent: number, serverNow: number, clientRecv: number): ClockSample {
    const s = estimateOffset(clientSent, serverNow, clientRecv);
    this.samples.push(s);
    if (this.samples.length > this.keep) this.samples.shift();
    return s;
  }

  get ready(): boolean {
    return this.samples.length > 0;
  }

  get best(): ClockSample | null {
    if (!this.samples.length) return null;
    return this.samples.reduce((a, b) => (b.rtt < a.rtt ? b : a));
  }

  /** Desfase a sumar a performance.now() para obtener el reloj del servidor (0 si aún no hay muestras). */
  get offset(): number {
    return this.best?.offset ?? 0;
  }

  /** Reloj del servidor estimado para un instante local de performance.now(). */
  serverTime(perfNow: number): number {
    return perfNow + this.offset;
  }
}
