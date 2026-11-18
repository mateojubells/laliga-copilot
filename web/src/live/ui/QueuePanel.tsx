import { useEffect, useRef, useState } from "react";
import { KIND_LABEL, ageLabel, ageMs, isStale, protagonists, reasonOf } from "../queue";
import type { LiveState, OperatorAction } from "../types";
import { OnDemand } from "./OnDemand";
import type { Roster } from "./useRoster";

export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

export function QueuePanel({
  state, selectedId, onSelect, send, roster, demandRef, follow,
}: {
  state: LiveState;
  selectedId: string | null;
  onSelect: (id: string) => void;
  send: (a: OperatorAction) => boolean;
  roster: Roster;
  demandRef: React.Ref<HTMLInputElement>;
  follow: boolean;
}) {
  const now = useNow();
  const onAirId = state.program?.graphic.id;
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <section className="op-col op-queue" aria-label="Cola">
      <OnDemand ref={demandRef} roster={roster} send={send} />
      <h2>Cola <span className="op-dim num">{state.order.length}</span>{follow && <span className="op-pill">sigue lo nuevo</span>}</h2>
      <ul className="op-list" ref={listRef} data-testid="queue">
        {state.order.length === 0 && <li className="op-empty">Sin propuestas todavía.</li>}
        {state.order.map((id) => {
          const it = state.graphics[id];
          if (!it) return null;
          const g = it.graphic;
          const live = id === onAirId;
          const stale = isStale(it, now, live);
          const r = reasonOf(g);
          const sel = id === selectedId;
          return (
            <li
              key={id} aria-selected={sel} data-testid="queue-item" data-id={id}
              className={`op-card ${sel ? "sel" : ""} ${live ? "live" : ""} ${it.auto ? "auto" : ""} ${stale ? "stale" : ""}`}
              onClick={() => onSelect(id)}
            >
              <div className="op-card__top">
                <span className="op-kind">{KIND_LABEL[g.kind] ?? g.kind}</span>
                {live && <span className="op-pill red">EN ANTENA</span>}
                {it.auto && !live && <span className="op-pill gold">AUTO</span>}
                {g.pinned && <span className="op-pill" title="Fijada: no caduca">📌</span>}
                <span className="op-dim num op-grow-r">P{g.priority ?? 50} · {ageLabel(ageMs(it, now))}</span>
              </div>
              <div className="op-who">{protagonists(g)}</div>
              <div className="op-why op-dim">
                {r.trigger}{r.text ? <> · «{r.text}»</> : null}
              </div>
              {sel && (
                <div className="op-acts">
                  <button type="button" className="op-btn sm primary" onClick={(e) => { e.stopPropagation(); send({ type: "take", graphic_id: id }); }}>A programa <kbd>↵</kbd></button>
                  <button type="button" className="op-btn sm" onClick={(e) => { e.stopPropagation(); send({ type: g.pinned ? "unpin" : "pin", graphic_id: id }); }}>{g.pinned ? "Soltar" : "Fijar"} <kbd>P</kbd></button>
                  <button type="button" className="op-btn sm danger" onClick={(e) => { e.stopPropagation(); send({ type: "discard", graphic_id: id }); }}>Descartar <kbd>Supr</kbd></button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <p className="op-keys op-dim">↑↓ mover · ↵ a programa · Supr descartar · P fijar · Esc quitar de programa · / a la carta</p>
    </section>
  );
}
