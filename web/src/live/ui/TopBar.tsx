import { useState } from "react";
import type { OperatorAction } from "../types";
import type { LiveState } from "../types";
import { fmtClock } from "./format";
import { EndMatch } from "./EndMatch";
import { MatchClock } from "./MatchClock";
import { ScoreEditor } from "./ScoreEditor";
import { VoiceControl } from "./VoiceControl";
import type { useReplayAudio } from "./useReplayAudio";

/** Saltos del audio del partido (segundos). Se arranca unos segundos antes para no perder la frase. */
export const JUMPS: { label: string; mark: number; lead: number }[] = [
  { label: "Inicio", mark: 23, lead: 0 },
  { label: "Gol 1-0", mark: 1200, lead: 15 },
  { label: "Gol 2-0", mark: 1420, lead: 15 },
  { label: "Gol 3-0", mark: 2820, lead: 15 },
  { label: "2.ª parte", mark: 3980, lead: 0 },
  { label: "Final", mark: 6808, lead: 30 },
];

export function TopBar({
  state, send, audio, serverNow = () => null, onEnded = () => undefined, showReplay = true, voiceSuggested = false,
}: {
  state: LiveState;
  send: (a: OperatorAction) => boolean;
  audio: ReturnType<typeof useReplayAudio>;
  /** Reloj del servidor estimado (ms) o null sin sincronía. */
  serverNow?: () => number | null;
  /** Se llamó a DELETE /api/session con éxito. */
  onEnded?: () => void;
  /** Mostrar los controles de repetición (sólo si el partido se configuró con voz "replay"). */
  showReplay?: boolean;
  /** La sesión usa micrófono: resalta el botón "Activar voz". */
  voiceSuggested?: boolean;
}) {
  const [speed, setSpeed] = useState(1);
  const [voice, setVoice] = useState(false);
  const m = state.match;
  const st = state.status;
  const replaying = !!st.replay;
  // con "Voz en vivo" el servidor pasa el audio por el motor de voz a velocidad real (siempre 1×)
  const start = (from: number, sp = speed) =>
    send({ type: "replay_control", value: "start", event: voice ? { from, speed: 1, mode: "voz" } : { from, speed: sp } });
  const changeSpeed = (sp: number) => {
    setSpeed(sp);
    if (replaying) start(Math.floor(audio.position()), sp);
  };
  const stop = () => { send({ type: "replay_control", value: "stop" }); audio.stop(); };
  const engineBad = (st.errors ?? 0) > 0;

  const clients = st.program_clients;

  return (
    <header className="op-top">
      <div className="op-row">
        <ScoreEditor match={m} send={send} />
        <MatchClock state={state} send={send} serverNow={serverNow} />
        <span className="op-grow-r" />
        <span
          className={`op-chip ${clients ? "ok" : "bad"}`} data-testid="op-program-chip"
          title="Páginas /program conectadas (la salida que va a OBS)"
        >
          <i /> {clients ? `Programa conectado (${clients})` : "Sin salida de programa"}
        </span>
        <a className="op-btn" href="/program" target="_blank" rel="noreferrer">Programa ↗</a>
        <button type="button" className="op-btn op-panic" onClick={() => send({ type: "panic" })} data-testid="op-panic" title="Vacía el programa y apaga el automático (Mayús+Esc)">
          PÁNICO <kbd>⇧Esc</kbd>
        </button>
        <EndMatch state={state} send={send} onEnded={onEnded} />
      </div>

      <div className="op-row">
        <VoiceControl state={state} send={send} suggested={voiceSuggested} />
        <button
          type="button" role="switch" aria-checked={state.autoProgram}
          className={`op-btn op-auto ${state.autoProgram ? "on" : ""}`}
          onClick={() => send({ type: "set_auto", value: !state.autoProgram })}
          title="Las propuestas de prioridad alta salen solas a programa"
        >
          Automático <b>{state.autoProgram ? "ON" : "OFF"}</b>
        </button>
        <div className="op-chips">
          <span className={`op-chip ${state.connected ? "ok" : "bad"}`} data-testid="op-conn" title="WebSocket">
            <i /> {state.connected ? "Conectado" : state.everConnected ? "Reconectando…" : "Sin conexión"}
          </span>
          <span className="op-chip" title="Datos">Datos · {st.data ?? "—"}</span>
          <span className={`op-chip ${engineBad ? "bad" : ""}`} title={st.last_error ?? "Sin errores"}>Errores · {st.errors ?? 0}</span>
        </div>
      </div>

      {showReplay && (
      <div className="op-replay" role="group" aria-label="Repetición">
        <span className="op-dim">Repetición</span>
        <button
          type="button" role="switch" aria-checked={voice} className={`op-btn sm ${voice ? "on" : ""}`}
          onClick={() => setVoice(!voice)} title="Pasa el audio por el motor de voz en vivo (velocidad real) en vez de usar la transcripción guardada"
        >
          Voz en vivo <b>{voice ? "ON" : "OFF"}</b>
        </button>
        {JUMPS.map((j) => (
          <button key={j.label} type="button" className="op-btn sm" title={`${fmtClock(j.mark)} en el audio`} onClick={() => start(j.mark - j.lead)}>
            {j.label}
          </button>
        ))}
        <span className="op-seg" role="group" aria-label="Velocidad">
          {[1, 2, 4].map((s) => (
            <button key={s} type="button" aria-pressed={speed === s} className={`op-btn sm ${speed === s ? "on" : ""}`} onClick={() => changeSpeed(s)}>{s}×</button>
          ))}
        </span>
        <button type="button" className="op-btn sm danger" disabled={!replaying} onClick={stop}>Parar</button>
        <button type="button" className="op-btn sm" aria-pressed={audio.muted} onClick={() => audio.setMuted(!audio.muted)}>
          {audio.muted ? "Sonido OFF" : "Sonido ON"}
        </button>
        {audio.blocked && <button type="button" className="op-btn sm warn" onClick={audio.activate}>Activar audio</button>}
        {replaying && <span className="op-chip ok" data-testid="op-replaying"><i /> en curso ×{st.replay?.speed ?? speed}</span>}
      </div>
      )}
      <audio ref={audio.ref} src="/api/replay/audio" preload="auto" />
    </header>
  );
}
