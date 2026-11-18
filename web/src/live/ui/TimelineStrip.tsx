import { useEffect, useRef, useState } from "react";
import type { LiveState, MatchEvent, OperatorAction } from "../types";
import { EVENT_LABEL, EVENT_TYPES } from "./format";
import type { Roster } from "./useRoster";

const ROLE_ORDER = ["actor", "receiver", "victim", "out"];
const ROLE_LABEL: Record<string, string> = { actor: "Protagonista", receiver: "Receptor", victim: "Afectado", out: "Sale", team_for: "Equipo a favor", team_against: "Equipo en contra" };
const STATUS_MARK: Record<string, string> = { auto: "", approved: "✓", edited: "✎", discarded: "✕" };

function who(ev: MatchEvent, roster: Roster): string {
  const names = ROLE_ORDER.filter((r) => ev.roles[r]).map((r) => roster.playerName(ev.roles[r]));
  if (names.length) return names.join(" · ");
  const t = ev.roles.team_for ?? ev.team;
  return t ? roster.teamShort(t) : "";
}

function PlayerSelect({ roster, value, onChange, label }: { roster: Roster; value: string; onChange: (v: string) => void; label: string }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      <option value="">— sin jugador —</option>
      {roster.teams.map((t) => (
        <optgroup key={t.id} label={t.name}>
          {roster.players.filter((p) => p.team.id === t.id).map((p) => <option key={p.id} value={p.id}>{p.number != null ? `${p.number} ` : ""}{p.known_as}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

function EventMenu({ ev, roster, send, close }: { ev: MatchEvent; roster: Roster; send: (a: OperatorAction) => boolean; close: () => void }) {
  const roles = Object.keys(ev.roles).filter((r) => !r.startsWith("team_"));
  const [role, setRole] = useState(roles[0] ?? "actor");
  const [pid, setPid] = useState(ev.roles[roles[0] ?? "actor"] ?? "");
  const edit = (event: Record<string, unknown>) => { send({ type: "edit_event", event_id: ev.id, event }); close(); };
  const fix = () => {
    if (!pid) return;
    const team = role === "actor" ? roster.teamOfPlayer(pid) : undefined;
    edit({ roles: { ...ev.roles, [role]: pid }, status: "edited", ...(team ? { team } : {}) });
  };
  return (
    <div className="op-pop" role="dialog" aria-label={`Evento ${ev.id}`} onClick={(e) => e.stopPropagation()}>
      <p className="op-pop__title"><b>{EVENT_LABEL[ev.type] ?? ev.type}</b> {ev.minute != null ? `${ev.minute}'` : ""} <span className="op-dim">{ev.status}</span></p>
      {ev.text && <p className="op-dim op-pop__text">«{ev.text}»</p>}
      <div className="op-pop__row">
        {ev.status !== "approved" && <button type="button" className="op-btn sm primary" onClick={() => edit({ status: "approved" })}>Aprobar</button>}
        {ev.status !== "discarded"
          ? <button type="button" className="op-btn sm danger" onClick={() => { send({ type: "discard_event", event_id: ev.id }); close(); }}>Descartar</button>
          : <button type="button" className="op-btn sm" onClick={() => edit({ status: "approved" })}>Restaurar</button>}
      </div>
      <div className="op-pop__row">
        <select value={role} onChange={(e) => { setRole(e.target.value); setPid(ev.roles[e.target.value] ?? ""); }} aria-label="Papel">
          {Array.from(new Set([...roles, "actor"])).map((r) => <option key={r} value={r}>{ROLE_LABEL[r] ?? r}</option>)}
        </select>
        <PlayerSelect roster={roster} value={pid} onChange={setPid} label="Jugador" />
        <button type="button" className="op-btn sm" disabled={!pid} onClick={fix}>Corregir</button>
      </div>
    </div>
  );
}

function AddEvent({ roster, send, close }: { roster: Roster; send: (a: OperatorAction) => boolean; close: () => void }) {
  const [type, setType] = useState("gol");
  const [pid, setPid] = useState("");
  const add = () => {
    const team = pid ? roster.teamOfPlayer(pid) : undefined;
    send({ type: "add_event", event: { type, roles: pid ? { actor: pid } : {}, ...(team ? { team } : {}), text: "(operador)" } });
    close();
  };
  return (
    <div className="op-pop" role="dialog" aria-label="Añadir evento" onClick={(e) => e.stopPropagation()}>
      <div className="op-pop__row">
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Tipo de evento">
          {EVENT_TYPES.map((t) => <option key={t} value={t}>{EVENT_LABEL[t]}</option>)}
        </select>
        <PlayerSelect roster={roster} value={pid} onChange={setPid} label="Jugador del evento" />
        <button type="button" className="op-btn sm primary" onClick={add}>Añadir</button>
      </div>
    </div>
  );
}

export function TimelineStrip({ state, roster, send }: { state: LiveState; roster: Roster; send: (a: OperatorAction) => boolean }) {
  // El menú es position:fixed (el carril hace scroll y recortaría un popover absoluto)
  const [open, setOpen] = useState<{ id: string; x: number; bottom: number } | null>(null);
  const [adding, setAdding] = useState<{ bottom: number } | null>(null);
  const openEv = open ? state.events.find((e) => e.id === open.id) : undefined;
  const rail = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = rail.current;
    if (el && stick.current) el.scrollLeft = el.scrollWidth;
  }, [state.events.length]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(null); setAdding(null); } };
    const c = () => { setOpen(null); setAdding(null); };
    window.addEventListener("keydown", k);
    window.addEventListener("click", c);
    return () => { window.removeEventListener("keydown", k); window.removeEventListener("click", c); };
  }, []);

  return (
    <section className="op-timeline" aria-label="Timeline">
      <h2>Timeline <span className="op-dim num">{state.events.length}</span></h2>
      <div
        className="op-rail" ref={rail} data-testid="timeline"
        onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollWidth - el.scrollLeft - el.clientWidth < 40; }}
      >
        {state.events.length === 0 && <span className="op-empty">Sin eventos: aparecerán según se hable del partido.</span>}
        {state.events.map((ev) => (
          <div key={ev.id} className="op-chipwrap">
            <button
              type="button" data-testid="event-chip" data-type={ev.type} data-status={ev.status}
              className={`op-ev ${ev.status} t-${ev.type}`}
              onClick={(e) => {
                e.stopPropagation();
                setAdding(null);
                const r = e.currentTarget.getBoundingClientRect();
                setOpen(open?.id === ev.id ? null : { id: ev.id, x: Math.min(r.left, window.innerWidth - 360), bottom: window.innerHeight - r.top + 6 });
              }}
            >
              <span className="op-ev__min num">{ev.minute != null ? `${ev.minute}'` : "—"}</span>
              <span className="op-ev__type">{EVENT_LABEL[ev.type] ?? ev.type}</span>
              <span className="op-ev__who">{who(ev, roster)}</span>
              <span className="op-ev__st" title={ev.status}>{STATUS_MARK[ev.status]}</span>
            </button>
          </div>
        ))}
      </div>
      <div className="op-add">
        <button
          type="button" className="op-btn"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(null);
            setAdding(adding ? null : { bottom: window.innerHeight - e.currentTarget.getBoundingClientRect().top + 6 });
          }}
        >+ evento</button>
      </div>
      {openEv && open && (
        <div className="op-popfix" style={{ left: open.x, bottom: open.bottom }}>
          <EventMenu key={openEv.id} ev={openEv} roster={roster} send={send} close={() => setOpen(null)} />
        </div>
      )}
      {adding && (
        <div className="op-popfix" style={{ right: 16, bottom: adding.bottom }}>
          <AddEvent roster={roster} send={send} close={() => setAdding(null)} />
        </div>
      )}
    </section>
  );
}
