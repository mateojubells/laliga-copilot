import { useEffect, useRef, useState } from "react";
import type { LiveState, OperatorAction } from "../types";
import { fmtClock } from "./format";

export function TranscriptPanel({ state, send }: { state: LiveState; send: (a: OperatorAction) => boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [text, setText] = useState("");

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [state.finals.length, state.partial?.text]);

  const submit = () => {
    const t = text.trim();
    if (!t) return;
    send({ type: "say", text: t });
    setText("");
  };

  return (
    <section className="op-col op-transcript" aria-label="Transcripción">
      <h2>Transcripción</h2>
      <div
        className="op-lines" ref={box} data-testid="transcript"
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {state.finals.length === 0 && !state.partial && <p className="op-empty">Esperando voz… escribe abajo para simularla o lanza una repetición.</p>}
        {state.finals.map((l) => (
          <p key={l.id} className="op-line">
            <time className="op-dim num">{fmtClock(l.t0)}</time> {l.text}
          </p>
        ))}
        {state.partial && (
          <p className="op-line partial" data-testid="partial">
            <time className="op-dim num">{fmtClock(state.partial.t0)}</time> {state.partial.text}
          </p>
        )}
      </div>
      <form className="op-say" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input
          value={text} onChange={(e) => setText(e.target.value)} placeholder="Simular voz… (Enter)"
          aria-label="Simular voz" data-testid="say-input"
          onKeyDown={(e) => { if (e.key === "Escape") e.currentTarget.blur(); }}
        />
      </form>
    </section>
  );
}
