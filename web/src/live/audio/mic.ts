import { backoffDelay } from "../client";

const LS_DEVICE = "lc.micDevice";

export function loadMicDevice(): string {
  try { return localStorage.getItem(LS_DEVICE) ?? ""; } catch { return ""; }
}
export function saveMicDevice(id: string): void {
  try { localStorage.setItem(LS_DEVICE, id); } catch { /* sin almacenamiento: no pasa nada */ }
}

export interface MicDevice { id: string; label: string }

/** Entradas de audio. Los nombres sólo están disponibles tras conceder el permiso. */
export async function listMicDevices(): Promise<MicDevice[]> {
  const all = await navigator.mediaDevices.enumerateDevices();
  return all
    .filter((d) => d.kind === "audioinput")
    .map((d, i) => ({ id: d.deviceId, label: d.label || `Micrófono ${i + 1}` }));
}

export type MicFailure = "denied" | "no-device" | "lost" | "unsupported" | "other";

export function micFailureText(f: MicFailure): string {
  switch (f) {
    case "denied": return "Permiso de micrófono denegado. Actívalo en la configuración del navegador.";
    case "no-device": return "No se encuentra el micrófono elegido.";
    case "lost": return "Se perdió el micrófono (desconectado o permiso retirado).";
    case "unsupported": return "Este navegador no permite capturar audio aquí (hace falta localhost o https).";
    default: return "No se pudo abrir el micrófono.";
  }
}

export class MicError extends Error {
  constructor(readonly failure: MicFailure) {
    super(micFailureText(failure));
  }
}

export interface MicCaptureOptions {
  deviceId?: string;
  /** Un trozo de 100 ms: PCM16 LE 16 kHz mono (3200 bytes) y su pico 0..1. */
  onChunk: (pcm: ArrayBuffer, peak: number) => void;
  /** La pista se cortó sola (dispositivo desconectado, permiso retirado). */
  onLost?: () => void;
}

/** Captura del micro con el AudioWorklet /pcm-worklet.js (sin cancelación de eco, ruido ni AGC: se quiere la señal tal cual). */
export class MicCapture {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  deviceLabel = "";

  async start(o: MicCaptureOptions): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioContext === "undefined") throw new MicError("unsupported");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          ...(o.deviceId ? { deviceId: { exact: o.deviceId } } : {}),
          echoCancellation: false, noiseSuppression: false, autoGainControl: false,
        },
      });
    } catch (e) {
      const name = (e as DOMException)?.name;
      throw new MicError(name === "NotAllowedError" || name === "SecurityError" ? "denied"
        : name === "NotFoundError" || name === "OverconstrainedError" ? "no-device" : "other");
    }
    try {
      const ctx = new AudioContext({ latencyHint: "interactive" });
      await ctx.audioWorklet.addModule("/pcm-worklet.js");
      const src = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, "pcm-16k", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1, channelCountMode: "explicit" });
      node.port.onmessage = (ev: MessageEvent<{ pcm: ArrayBuffer; peak: number }>) => o.onChunk(ev.data.pcm, ev.data.peak);
      // Algunos navegadores sólo "tiran" del worklet si llega a la salida: va a un nodo mudo.
      const mute = ctx.createGain();
      mute.gain.value = 0;
      src.connect(node).connect(mute).connect(ctx.destination);
      const track = stream.getAudioTracks()[0];
      this.deviceLabel = track?.label ?? "";
      if (track) track.onended = () => { if (this.stream === stream) o.onLost?.(); };
      this.ctx = ctx; this.stream = stream; this.node = node;
      if (ctx.state === "suspended") await ctx.resume();
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      throw new MicError("other");
    }
  }

  stop(): void {
    const { ctx, stream, node } = this;
    this.ctx = null; this.stream = null; this.node = null;
    if (node) node.port.onmessage = null;
    stream?.getTracks().forEach((t) => { t.onended = null; t.stop(); });
    void ctx?.close().catch(() => undefined);
  }
}

export function audioWsUrl(): string {
  const proto = typeof location !== "undefined" && location.protocol === "https:" ? "wss" : "ws";
  const host = typeof location !== "undefined" && location.host ? location.host : "127.0.0.1:8765";
  return `${proto}://${host}/ws/audio`;
}

/** WebSocket binario /ws/audio con reconexión. Si está caído se descartan trozos (audio atrasado no sirve en directo). */
export class AudioSocket {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private stopped = true;
  private retry: ReturnType<typeof setTimeout> | undefined;
  constructor(private readonly onState?: (open: boolean) => void, private readonly url: string = audioWsUrl()) {}

  get open(): boolean { return this.ws?.readyState === 1; }

  start(): void { this.stopped = false; this.connect(); }

  stop(): void {
    this.stopped = true;
    clearTimeout(this.retry);
    const ws = this.ws;
    this.ws = null;
    if (ws) { ws.onopen = ws.onclose = ws.onerror = null; try { ws.close(); } catch { /* nada */ } }
    this.onState?.(false);
  }

  send(pcm: ArrayBuffer): boolean {
    if (!this.ws || this.ws.readyState !== 1) return false;
    try { this.ws.send(pcm); return true; } catch { return false; }
  }

  private connect(): void {
    if (this.stopped) return;
    let ws: WebSocket;
    try { ws = new WebSocket(this.url); } catch { this.schedule(); return; }
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => { this.attempt = 0; this.onState?.(true); };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.onState?.(false);
      this.schedule();
    };
    ws.onerror = () => { /* el cierre posterior reintenta */ };
  }

  private schedule(): void {
    if (this.stopped) return;
    clearTimeout(this.retry);
    this.retry = setTimeout(() => this.connect(), backoffDelay(this.attempt++, 300, 4000));
  }
}
