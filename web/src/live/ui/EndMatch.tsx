import { useEffect, useState } from "react";
import { api } from "../api";
import { phaseOf } from "../matchClock";
import type { LiveState, OperatorAction } from "../types";

/** Terminar partido: confirmación en la interfaz → clock full_time (si falta) → voice stop → DELETE /api/session → /setup. */
export function EndMatch({ state, send, onEnded }: { state: LiveState; send: (a: OperatorAction) => boolean; onEnded: () => void }) {
  const [ask, setAsk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!ask) return;
    const t = setTimeout(() => setAsk(false), 8000);
    return () => clearTimeout(t);
  }, [ask]);

  const end = async () => {
    setBusy(true); setErr(null);
    try {
      if (phaseOf(state.match) !== "final") send({ type: "clock", value: "full_time" });
      send({ type: "voice", value: "stop" });
      await api.endSession();
      onEnded();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };

  if (!ask) {
    return <button type="button" className="op-btn" onClick={() => setAsk(true)} data-testid="op-end">Terminar partido</button>;
  }
  return (
    <span className="op-confirm" role="alertdialog" aria-label="Confirmar fin del partido">
      <span>¿Terminar y archivar el partido?</span>
      <button type="button" className="op-btn sm danger" disabled={busy} onClick={() => void end()} data-testid="op-end-confirm">{busy ? "Terminando…" : "Sí, terminar"}</button>
      <button type="button" className="op-btn sm" disabled={busy} onClick={() => setAsk(false)}>No</button>
      {err && <span className="op-chip bad" role="alert">{err}</span>}
    </span>
  );
}
