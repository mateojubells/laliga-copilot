import { forwardRef, useId, useState } from "react";
import { GRAPHIC_KINDS } from "../../contracts";
import { KIND_LABEL } from "../queue";
import type { OperatorAction } from "../types";
import type { Roster } from "./useRoster";

/** Resuelve texto libre o etiqueta del autocompletar a un id de jugador/equipo. */
export function resolveEntity(text: string, roster: Roster): string | undefined {
  const t = text.trim().toLowerCase();
  if (!t) return undefined;
  const opts = [
    ...roster.players.map((p) => ({ id: p.id, keys: [p.known_as, p.name, `${p.known_as} (${p.team.short})`] })),
    ...roster.teams.map((x) => ({ id: x.id, keys: [x.name, x.short] })),
  ];
  const hit = opts.find((o) => o.keys.some((k) => k.toLowerCase() === t)) ?? opts.find((o) => o.keys.some((k) => k.toLowerCase().includes(t)));
  return hit?.id;
}

/** "A la carta": pide un grafismo manualmente. La tecla "/" enfoca el campo de jugador/equipo. */
export const OnDemand = forwardRef<HTMLInputElement, { roster: Roster; send: (a: OperatorAction) => boolean }>(function OnDemand({ roster, send }, ref) {
  const listId = useId();
  const [kind, setKind] = useState<string>("player_card");
  const [subject, setSubject] = useState("");
  const [other, setOther] = useState("");
  const [msg, setMsg] = useState("");

  const submit = () => {
    const s = resolveEntity(subject, roster);
    const o = resolveEntity(other, roster);
    if (subject.trim() && !s) return setMsg("No encuentro a «" + subject + "»");
    if (other.trim() && !o) return setMsg("No encuentro a «" + other + "»");
    const ok = send({ type: "request", request: { kind, subject: s ?? null, other: o ?? null } });
    setMsg(ok ? "Pedido…" : "Sin conexión");
    if (ok) { setSubject(""); setOther(""); (document.activeElement as HTMLElement | null)?.blur(); } // el teclado vuelve a la cola (↵ = a programa)
  };
  const blurOnEsc = (e: React.KeyboardEvent<HTMLElement>) => { if (e.key === "Escape") (e.currentTarget as HTMLElement).blur(); };

  return (
    <form className="op-demand" onSubmit={(e) => { e.preventDefault(); submit(); }} aria-label="A la carta">
      <h2>A la carta <kbd>/</kbd></h2>
      <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Tipo de grafismo" onKeyDown={blurOnEsc}>
        {GRAPHIC_KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k] ?? k}</option>)}
      </select>
      <input ref={ref} list={listId} value={subject} onChange={(e) => { setSubject(e.target.value); setMsg(""); }} placeholder="Jugador o equipo" aria-label="Jugador o equipo" data-testid="demand-subject" onKeyDown={blurOnEsc} />
      <input list={listId} value={other} onChange={(e) => { setOther(e.target.value); setMsg(""); }} placeholder="Otro (comparar, conexión…)" aria-label="Otro jugador o equipo" onKeyDown={blurOnEsc} />
      <datalist id={listId}>
        {roster.teams.map((t) => <option key={t.id} value={t.name} />)}
        {roster.players.map((p) => <option key={p.id} value={p.known_as}>{p.team.short} · {p.name}</option>)}
      </datalist>
      <button type="submit" className="op-btn">Pedir</button>
      {msg && <span className="op-dim op-msg">{msg}</span>}
    </form>
  );
});
