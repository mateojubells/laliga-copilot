import { useCallback, useEffect, useRef, useState } from "react";
import { AudioSocket, MicCapture, MicError, listMicDevices, loadMicDevice, micFailureText } from "../audio/mic";
import { levelToMeter } from "../audio/meter";
import type { LiveState, OperatorAction } from "../types";

/** Meter horizontal 0..1. */
export function Meter({ value, label, className = "" }: { value: number; label: string; className?: string }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <span className={`op-meter ${className}`} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={1} aria-valuenow={Number(v.toFixed(2))} title={label}>
      <i style={{ width: `${Math.round(v * 100)}%` }} className={v > 0.92 ? "hot" : ""} />
    </span>
  );
}

const VOICE_TEXT: Record<string, string> = { off: "apagado", starting: "arrancando…", on: "escuchando", error: "con error" };

/**
 * Micrófono del operador: captura (getUserMedia + AudioWorklet), WebSocket binario /ws/audio y acciones voice start/stop.
 * El audio sólo sale del navegador mientras esté activo.
 */
export function VoiceControl({ state, send, suggested }: { state: LiveState; send: (a: OperatorAction) => boolean; suggested?: boolean }) {
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const [label, setLabel] = useState("");
  const [audioUp, setAudioUp] = useState(false);
  const capRef = useRef<MicCapture | null>(null);
  const sockRef = useRef<AudioSocket | null>(null);
  const activeRef = useRef(false);

  const teardown = useCallback(() => {
    capRef.current?.stop(); capRef.current = null;
    sockRef.current?.stop(); sockRef.current = null;
    activeRef.current = false;
    setActive(false); setLevel(0); setAudioUp(false);
  }, []);

  const stop = useCallback((reason?: string) => {
    if (activeRef.current) send({ type: "voice", value: "stop" });
    teardown();
    if (reason) setError(reason);
  }, [send, teardown]);

  const start = useCallback(async () => {
    setBusy(true); setError(null);
    const cap = new MicCapture();
    const sock = new AudioSocket(setAudioUp);
    const opts = {
      onChunk: (pcm: ArrayBuffer, peak: number) => { sock.send(pcm); setLevel(levelToMeter(peak)); },
      onLost: () => stop(micFailureText("lost")),
    };
    try {
      const wanted = loadMicDevice();
      try {
        await cap.start({ ...opts, deviceId: wanted || undefined });
      } catch (e) {
        // el dispositivo guardado ya no existe: se prueba el predeterminado antes de rendirse
        if (wanted && e instanceof MicError && e.failure === "no-device") await cap.start(opts);
        else throw e;
      }
      capRef.current = cap; sockRef.current = sock; activeRef.current = true;
      sock.start();
      send({ type: "voice", value: "start" });
      setActive(true);
      setLabel(cap.deviceLabel || (await listMicDevices().catch(() => []))[0]?.label || "micrófono");
    } catch (e) {
      cap.stop(); sock.stop();
      setError(e instanceof MicError ? e.message : micFailureText("other"));
    } finally {
      setBusy(false);
    }
  }, [send, stop]);

  // Si el WebSocket de control se reconecta con la voz activa, hay que volver a pedir el arranque.
  useEffect(() => {
    if (state.connected && activeRef.current) send({ type: "voice", value: "start" });
  }, [state.connected, send]);

  useEffect(() => () => { teardown(); }, [teardown]);

  const st = state.status;
  const engine = st.voice ? VOICE_TEXT[st.voice] ?? st.voice : null;

  return (
    <div className="op-voice" role="group" aria-label="Micrófono" data-testid="op-voice">
      <button
        type="button" role="switch" aria-checked={active} disabled={busy}
        className={`op-btn ${active ? "on" : suggested ? "warn" : ""}`}
        onClick={() => (active ? stop() : void start())}
        title={active ? "Apagar el micrófono y el motor de voz" : "Encender el micrófono y el motor de voz"}
      >
        {busy ? "Abriendo…" : active ? "Voz ON" : "Activar voz"}
      </button>
      {active && <span className="op-voice__dev op-ellipsis" title={label}>{label}</span>}
      <Meter value={active ? level : 0} label="Nivel del micrófono" />
      {active && (
        <span className={`op-chip ${audioUp ? "ok" : "bad"}`} title="WebSocket de audio al servidor"><i /> {audioUp ? "Audio" : "Sin audio"}</span>
      )}
      <span className="op-chip" title={st.asr ?? "motor de voz"}>
        Motor · {engine ?? "—"}{st.asr ? ` (${st.asr})` : ""}
        {active && st.mic_level != null && <Meter value={levelToMeter(st.mic_level)} label="Nivel que recibe el servidor" className="srv" />}
      </span>
      {error && <span className="op-chip bad op-voice__err" role="alert">{error}</span>}
    </div>
  );
}
