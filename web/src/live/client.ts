import { ClockSync } from "./clock";
import type { OperatorAction, Role, ServerMsg } from "./types";

export interface LiveClientOptions {
  role: Role;
  onMessage: (msg: ServerMsg) => void;
  onConnection?: (connected: boolean) => void;
  url?: string;
  /** Inyectable en tests. */
  WebSocketCtor?: typeof WebSocket;
  perfNow?: () => number;
  pingEveryMs?: number;
  /** Espera de reconexión: min(base·2^intento, max). */
  backoff?: { base: number; max: number };
}

export function wsUrl(role: Role): string {
  const proto = typeof location !== "undefined" && location.protocol === "https:" ? "wss" : "ws";
  const host = typeof location !== "undefined" && location.host ? location.host : "127.0.0.1:8765";
  return `${proto}://${host}/ws?role=${role}`;
}

export function backoffDelay(attempt: number, base = 500, max = 8000): number {
  return Math.min(base * 2 ** attempt, max);
}

/** WebSocket con reconexión de espera creciente, ping de reloj cada 10 s y colas silenciosas (no lanza nunca). */
export class LiveClient {
  readonly clock = new ClockSync();
  private ws: WebSocket | null = null;
  private attempt = 0;
  private stopped = true;
  private retry: ReturnType<typeof setTimeout> | undefined;
  private pinger: ReturnType<typeof setInterval> | undefined;
  private readonly perf: () => number;

  constructor(private readonly o: LiveClientOptions) {
    this.perf = o.perfNow ?? (() => performance.now());
  }

  get connected(): boolean {
    return this.ws?.readyState === 1;
  }

  start(): void {
    this.stopped = false;
    this.open();
  }

  stop(): void {
    this.stopped = true;
    clearTimeout(this.retry);
    clearInterval(this.pinger);
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
      try { ws.close(); } catch { /* nada */ }
    }
  }

  send(action: OperatorAction): boolean {
    if (!this.ws || this.ws.readyState !== 1) return false;
    try {
      this.ws.send(JSON.stringify(action));
      return true;
    } catch {
      return false;
    }
  }

  /** Reloj del servidor estimado para este instante. */
  serverNow(): number {
    return this.clock.serverTime(this.perf());
  }

  private open(): void {
    if (this.stopped) return;
    const Ctor = this.o.WebSocketCtor ?? WebSocket;
    let ws: WebSocket;
    try {
      ws = new Ctor(this.o.url ?? wsUrl(this.o.role));
    } catch {
      this.scheduleRetry();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.attempt = 0;
      this.o.onConnection?.(true);
      this.ping();
      clearInterval(this.pinger);
      this.pinger = setInterval(() => this.ping(), this.o.pingEveryMs ?? 10_000);
    };
    ws.onmessage = (ev) => {
      let msg: ServerMsg;
      try { msg = JSON.parse(String(ev.data)) as ServerMsg; } catch { return; }
      const d = msg.data as { client_now?: number } | null | undefined;
      if (msg.type === "hello" && d && typeof d.client_now === "number") {
        this.clock.add(d.client_now, msg.server_now, this.perf());
      }
      this.o.onMessage(msg);
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      clearInterval(this.pinger);
      this.o.onConnection?.(false);
      this.scheduleRetry();
    };
    ws.onerror = () => { /* el cierre posterior reintenta; nunca se muestra nada */ };
  }

  private ping(): void {
    this.send({ type: "ping", client_now: this.perf() });
  }

  private scheduleRetry(): void {
    if (this.stopped) return;
    const b = this.o.backoff ?? { base: 500, max: 8000 };
    const delay = backoffDelay(this.attempt++, b.base, b.max);
    clearTimeout(this.retry);
    this.retry = setTimeout(() => this.open(), delay);
  }
}
