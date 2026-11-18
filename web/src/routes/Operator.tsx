import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useLive } from "../live";
import { useSessionGuard } from "../live/useSessionGuard";
import { LatencyPanel } from "../live/ui/LatencyPanel";
import { Monitors } from "../live/ui/Monitors";
import { QueuePanel } from "../live/ui/QueuePanel";
import { TimelineStrip } from "../live/ui/TimelineStrip";
import { TopBar } from "../live/ui/TopBar";
import { TranscriptPanel } from "../live/ui/TranscriptPanel";
import { useReplayAudio } from "../live/ui/useReplayAudio";
import { useRoster } from "../live/ui/useRoster";
import "./Operator.css";

const typing = (t: EventTarget | null) => {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
};

/** "/" : sin partido en curso (GET /api/session con config null) redirige al menú /setup. */
export function Operator() {
  const guard = useSessionGuard();
  if (guard.status === "none") return <Navigate to="/setup" replace />;
  if (guard.status === "loading") return <div className="op op-loading" data-testid="operator-loading"><p className="op-dim">Comprobando el partido en curso…</p></div>;
  return <OperatorView voice={guard.status === "active" ? guard.info.config?.voice : undefined} sessionError={guard.status === "error" ? guard.message : null} />;
}

/** Vista de operador (docs/ARCHITECTURE.md §9): transcripción, cola, monitores, timeline y latencias. */
function OperatorView({ voice, sessionError }: { voice?: string; sessionError: string | null }) {
  const navigate = useNavigate();
  const { state, send, reportPainted, clientRef } = useLive("operator");
  const serverNow = useCallback(() => {
    const c = clientRef.current;
    return c && c.clock.ready ? c.serverNow() : null;
  }, [clientRef]);
  const roster = useRoster();
  const audio = useReplayAudio(state);
  const demandRef = useRef<HTMLInputElement>(null);

  // Selección: por defecto sigue a lo más nuevo; al mover con flechas o hacer clic se queda donde está.
  const [picked, setPicked] = useState<string | null>(null);
  const follow = picked == null || !state.graphics[picked];
  const selectedId = follow ? (state.order[0] ?? null) : picked;
  const preview = selectedId ? state.graphics[selectedId]?.graphic ?? null : null;

  const sel = useRef({ order: state.order, selectedId, graphics: state.graphics, program: state.program });
  sel.current = { order: state.order, selectedId, graphics: state.graphics, program: state.program };

  const keydown = useCallback((e: KeyboardEvent) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "Escape" && e.shiftKey) { e.preventDefault(); send({ type: "panic" }); return; } // pánico: funciona incluso escribiendo
    if (typing(e.target)) return; // los campos gestionan sus propias teclas (Esc los suelta)
    const { order, selectedId: id, graphics, program } = sel.current;
    const idx = id ? order.indexOf(id) : -1;
    switch (e.key) {
      case "ArrowDown":
      case "ArrowUp": {
        e.preventDefault();
        if (!order.length) return;
        const next = e.key === "ArrowDown" ? Math.min(order.length - 1, idx + 1) : Math.max(0, idx - 1);
        setPicked(order[next]);
        break;
      }
      case "Enter":
        if (id) { e.preventDefault(); send({ type: "take", graphic_id: id }); setPicked(null); }
        break;
      case "Delete":
      case "Backspace":
        if (id) {
          e.preventDefault();
          send({ type: "discard", graphic_id: id });
          setPicked(order[idx + 1] ?? order[idx - 1] ?? null); // el siguiente de la cola, no un salto al más nuevo
        }
        break;
      case "p":
      case "P":
        if (id && graphics[id]) { e.preventDefault(); send({ type: graphics[id].graphic.pinned ? "unpin" : "pin", graphic_id: id }); }
        break;
      case "Escape":
        if (program) { e.preventDefault(); send({ type: "clear_program" }); }
        break;
      case "/":
        e.preventDefault();
        demandRef.current?.focus();
        break;
    }
  }, [send]);

  useEffect(() => {
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [keydown]);

  const clear = useMemo(() => () => send({ type: "clear_program" }), [send]);

  return (
    <div className="op" data-testid="operator">
      <div>
        <TopBar
          state={state} send={send} audio={audio} serverNow={serverNow} onEnded={() => navigate("/setup")}
          showReplay={voice === "replay" || voice === undefined} voiceSuggested={voice === "mic"}
        />
        {sessionError && <p className="op-banner" role="alert">No se pudo comprobar el partido en curso ({sessionError}) Reintentando…</p>}
      </div>
      <div className="op-main">
        <div className="op-left">
          <TranscriptPanel state={state} send={send} />
          <LatencyPanel />
        </div>
        <Monitors state={state} preview={preview} onClear={clear} reportPainted={reportPainted} />
        <QueuePanel
          state={state} selectedId={selectedId} onSelect={setPicked} send={send} roster={roster}
          demandRef={demandRef} follow={follow}
        />
      </div>
      <TimelineStrip state={state} roster={roster} send={send} />
    </div>
  );
}
