import { useCallback, useEffect, useRef, useState } from "react";
import type { LiveState } from "../types";

/**
 * Reproduce /api/replay/audio sincronizado con la repetición del servidor.
 * Al llegar status.replay_started {audio_t, speed}: currentTime = audio_t, playbackRate = speed, play().
 * Si el navegador bloquea el autoplay, `blocked` pasa a true y hay que llamar a `activate()` desde un clic.
 */
export function useReplayAudio(state: Pick<LiveState, "replayStarted" | "status">) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [muted, setMuted] = useState(false);
  const started = state.replayStarted;
  const running = !!state.status.replay;
  const wasRunning = useRef(false);

  const play = useCallback((t: number, speed: number) => {
    const a = ref.current;
    if (!a) return;
    const go = () => {
      a.currentTime = t;
      a.playbackRate = speed;
      a.play().then(() => setBlocked(false)).catch(() => setBlocked(true));
    };
    if (a.readyState >= 1) go();
    else {
      a.addEventListener("loadedmetadata", go, { once: true });
      a.load();
    }
  }, []);

  useEffect(() => {
    if (started) play(started.audio_t, started.speed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started?.n]);

  // El servidor terminó o paró la repetición: se calla el audio.
  useEffect(() => {
    if (wasRunning.current && !running) ref.current?.pause();
    wasRunning.current = running;
  }, [running]);

  useEffect(() => { if (ref.current) ref.current.muted = muted; }, [muted]);

  const activate = useCallback(() => {
    if (started) play(ref.current?.currentTime ?? started.audio_t, started.speed);
  }, [play, started]);
  const stop = useCallback(() => { ref.current?.pause(); setBlocked(false); }, []);
  const position = useCallback(() => ref.current?.currentTime ?? 0, []);

  return { ref, blocked, muted, setMuted, activate, stop, position };
}
