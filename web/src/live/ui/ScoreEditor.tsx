import { useState } from "react";
import type { MatchState } from "../../contracts";
import type { OperatorAction } from "../types";

/** Marcador de la barra; al hacer clic abre un editor con +/− por equipo que envía set_score al aplicar. */
export function ScoreEditor({ match, send }: { match: MatchState | null; send: (a: OperatorAction) => boolean }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<[number, number]>([0, 0]);
  if (!match) return <span className="op-dim">sin partido</span>;
  const h = match.home_goals ?? 0, a = match.away_goals ?? 0;
  const toggle = () => { if (!open) setDraft([h, a]); setOpen(!open); };
  const bump = (i: 0 | 1, d: number) => setDraft((x) => (i === 0 ? [Math.max(0, x[0] + d), x[1]] : [x[0], Math.max(0, x[1] + d)]));
  const apply = () => { send({ type: "set_score", event: { home: draft[0], away: draft[1] } }); setOpen(false); };

  return (
    <span className="op-popwrap">
      <button type="button" className="op-score op-score__btn" onClick={toggle} aria-expanded={open} title="Clic para corregir el marcador" data-testid="op-score">
        <span>{match.home.short}</span>
        <b className="display num">{h}–{a}</b>
        <span>{match.away.short}</span>
      </button>
      {open && (
        <div className="op-dropdown" role="dialog" aria-label="Corregir marcador" data-testid="op-score-editor">
          {([match.home, match.away] as const).map((t, i) => (
            <div key={t.id} className="op-dropdown__row">
              <span className="op-grow">{t.short}</span>
              <button type="button" className="op-btn sm" aria-label={`Quitar un gol a ${t.short}`} onClick={() => bump(i as 0 | 1, -1)} disabled={draft[i] <= 0}>−</button>
              <b className="num op-dropdown__n">{draft[i]}</b>
              <button type="button" className="op-btn sm" aria-label={`Añadir un gol a ${t.short}`} onClick={() => bump(i as 0 | 1, 1)}>+</button>
            </div>
          ))}
          <div className="op-dropdown__row">
            <button type="button" className="op-btn sm primary" onClick={apply} disabled={draft[0] === h && draft[1] === a}>Aplicar</button>
            <button type="button" className="op-btn sm" onClick={() => setOpen(false)}>Cancelar</button>
          </div>
        </div>
      )}
    </span>
  );
}
