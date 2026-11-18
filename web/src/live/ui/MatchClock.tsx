import { useEffect, useState } from "react";
import { PHASE_LABEL, clockSeconds, fmtMatchClock, periodControl, phaseOf } from "../matchClock";
import type { LiveState, OperatorAction } from "../types";

/** Reloj corriendo en el cliente: se repinta 4 veces por segundo a partir de MatchState y el desfase de reloj. */
export function MatchClock({
  state, send, serverNow,
}: {
  state: LiveState;
  send: (a: OperatorAction) => boolean;
  /** Reloj del servidor estimado (ms) o null si aún no hay muestra de sincronía. */
  serverNow: () => number | null;
}) {
  const m = state.match;
  const [, force] = useState(0);
  useEffect(() => {
    const t = setInterval(() => force((n) => n + 1), 250);
    return () => clearInterval(t);
  }, []);

  const secs = clockSeconds(m, serverNow());
  const phase = phaseOf(m);
  const ctl = periodControl(m);
  const added = m?.added ?? 0;
  const [confirming, setConfirming] = useState(false);
  const [adjust, setAdjust] = useState(false);
  const [minute, setMinute] = useState("");

  useEffect(() => {
    if (!confirming) return;
    const t = setTimeout(() => setConfirming(false), 6000);
    return () => clearTimeout(t);
  }, [confirming]);
  useEffect(() => setConfirming(false), [phase]);

  const fire = () => {
    if (!ctl) return;
    send({ type: "clock", value: ctl.value });
    setConfirming(false);
  };
  const setMin = () => {
    const n = Number(minute);
    if (!Number.isFinite(n) || minute.trim() === "" || n < 0 || n > 130) return;
    send({ type: "clock", value: "set_minute", event: { minute: Math.floor(n), second: 0 } });
    setMinute(""); setAdjust(false);
  };
  const setAdded = (n: number) => send({ type: "clock", value: "set_added", event: { minutes: Math.max(0, Math.min(15, n)) } });

  return (
    <div className="op-clock" data-testid="op-clock" role="group" aria-label="Reloj del partido">
      <div className="op-clock__face">
        <b className="display num" data-testid="op-clock-time">{fmtMatchClock(secs)}</b>
        {added > 0 && <span className="op-clock__added" data-testid="op-clock-added">+{added}</span>}
        <span className={`op-clock__phase ${m?.clock_running ? "run" : ""}`} data-testid="op-clock-phase">{PHASE_LABEL[phase]}</span>
      </div>

      {ctl && !confirming && (
        <button type="button" className={`op-btn op-clock__go ${ctl.confirm ? "danger" : "primary"}`} disabled={!m}
          onClick={() => (ctl.confirm ? setConfirming(true) : fire())} data-testid="op-clock-btn">
          {ctl.label}
        </button>
      )}
      {ctl && confirming && (
        <span className="op-confirm" role="alertdialog" aria-label="Confirmar final del partido">
          <span>¿Pitar el final?</span>
          <button type="button" className="op-btn sm danger" onClick={fire} data-testid="op-clock-confirm">Sí, final</button>
          <button type="button" className="op-btn sm" onClick={() => setConfirming(false)}>No</button>
        </span>
      )}
      {!ctl && <span className="op-chip" data-testid="op-clock-done">Partido terminado</span>}

      <span className="op-popwrap">
        <button type="button" className="op-btn sm" aria-expanded={adjust} onClick={() => setAdjust(!adjust)} title="Ajustar minuto y descuento">Ajustar</button>
        {adjust && (
          <div className="op-dropdown" role="dialog" aria-label="Ajustar reloj">
            <label className="op-dropdown__row">Minuto
              <input type="number" min={0} max={130} inputMode="numeric" value={minute} placeholder={String(Math.floor(secs / 60))}
                onChange={(e) => setMinute(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") setMin(); }} />
              <button type="button" className="op-btn sm primary" onClick={setMin} disabled={minute.trim() === ""}>Fijar</button>
            </label>
            <div className="op-dropdown__row">Descuento
              <button type="button" className="op-btn sm" aria-label="Quitar un minuto de descuento" onClick={() => setAdded(added - 1)} disabled={added <= 0}>−</button>
              <b className="num" data-testid="op-added">+{added}</b>
              <button type="button" className="op-btn sm" aria-label="Añadir un minuto de descuento" onClick={() => setAdded(added + 1)}>+</button>
            </div>
          </div>
        )}
      </span>
    </div>
  );
}
