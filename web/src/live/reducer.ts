import type { MatchEvent, LiveAction, LiveState, QueueItem, ServerMsg, TranscriptLine } from "./types";
import { MAX_QUEUE, isExpired } from "./queue";

const MAX_FINALS = 600;

export function initialState(): LiveState {
  return {
    connected: false,
    everConnected: false,
    match: null,
    finals: [],
    partial: null,
    graphics: {},
    order: [],
    program: null,
    events: [],
    status: {},
    autoProgram: false,
    replayStarted: null,
  };
}

const byTime = (a: MatchEvent, b: MatchEvent) => a.t_audio - b.t_audio;

function toLine(t: Record<string, unknown>): TranscriptLine {
  return {
    id: String(t.trace_id ?? `${t.t0}-${t.text}`),
    text: String(t.text ?? ""),
    t0: Number(t.t0 ?? 0),
    t1: Number(t.t1 ?? 0),
    engine: typeof t.engine === "string" ? t.engine : undefined,
  };
}

function mergeStatus(s: LiveState, data: Record<string, unknown>): LiveState {
  const { replay_started, auto_program, ...rest } = data;
  let next: LiveState = { ...s, status: { ...s.status, ...(rest as object) } };
  if (typeof auto_program === "boolean") next = { ...next, autoProgram: auto_program };
  if (replay_started && typeof replay_started === "object") {
    const r = replay_started as { audio_t?: number; speed?: number };
    next = { ...next, replayStarted: { audio_t: Number(r.audio_t ?? 0), speed: Number(r.speed ?? 1), n: (s.replayStarted?.n ?? 0) + 1 } };
  }
  return next;
}

function applyEvent(events: MatchEvent[], ev: Record<string, unknown>): MatchEvent[] {
  const action = ev.action;
  if (action === "reload") return [...((ev.events as MatchEvent[]) ?? [])].sort(byTime);
  const { action: _a, ...rest } = ev;
  const me = rest as unknown as MatchEvent;
  if (!me.id) return events;
  if (action === "retract") return events.filter((e) => e.id !== me.id);
  const i = events.findIndex((e) => e.id === me.id);
  if (i < 0) return [...events, me].sort(byTime); // "new" (o "update" de uno que no teníamos)
  const copy = events.slice();
  copy[i] = me;
  return copy.sort(byTime);
}

function putGraphic(s: LiveState, g: QueueItem["graphic"], now: number): LiveState {
  const prev = s.graphics[g.id];
  const graphics = { ...s.graphics, [g.id]: { graphic: g, receivedAt: prev?.receivedAt ?? now, auto: prev?.auto ?? g.state === "on_air" } };
  let order = prev ? s.order : [g.id, ...s.order];
  if (order.length > MAX_QUEUE) {
    for (const id of order.slice(MAX_QUEUE)) delete graphics[id];
    order = order.slice(0, MAX_QUEUE);
  }
  return { ...s, graphics, order };
}

function onMsg(s: LiveState, msg: ServerMsg, now: number): LiveState {
  switch (msg.type) {
    case "hello": {
      let next = s;
      if (msg.state) next = { ...next, match: msg.state };
      const d = msg.data as Record<string, unknown> | null | undefined;
      if (d && typeof d.status === "object" && d.status) next = mergeStatus(next, d.status as Record<string, unknown>);
      if (d && typeof d.auto_program === "boolean") next = { ...next, autoProgram: d.auto_program };
      return next;
    }
    case "state":
      return msg.state ? { ...s, match: msg.state } : s;
    case "status":
      return msg.data ? mergeStatus(s, msg.data as Record<string, unknown>) : s;
    case "transcript": {
      if (!msg.transcript) return s;
      const t = msg.transcript as Record<string, unknown>;
      const line = toLine(t);
      if (!t.final) return line.text.trim() ? { ...s, partial: line } : { ...s, partial: null };
      if (!line.text.trim()) return { ...s, partial: null };
      if (s.finals.some((f) => f.id === line.id)) return { ...s, partial: null };
      const finals = [...s.finals, line];
      return { ...s, finals: finals.length > MAX_FINALS ? finals.slice(-MAX_FINALS) : finals, partial: null };
    }
    case "graphic":
      return msg.graphic ? putGraphic(s, msg.graphic, now) : s;
    case "graphic_hide": {
      const id = msg.graphic_id;
      if (!id || !s.graphics[id]) return s;
      const { [id]: _gone, ...graphics } = s.graphics;
      return { ...s, graphics, order: s.order.filter((x) => x !== id) };
    }
    case "program": {
      if (!msg.graphic) return s;
      const g = { ...msg.graphic, state: "on_air" as const };
      // El servidor reenvía el grafismo en antena al (re)conectar aunque ya haya vencido su ttl: la edad se mide con
      // sus propias marcas (server_now − ts.ws_send, mismo reloj), sin necesidad de sincronizar relojes.
      const age = Math.max(0, msg.server_now - (g.ts?.ws_send ?? msg.server_now));
      if (!g.pinned && age >= (g.ttl_ms ?? 12000)) return s.program ? { ...s, program: null } : s;
      const q = s.graphics[g.id];
      return { ...s, program: { graphic: g, since: now - age }, graphics: q ? { ...s.graphics, [g.id]: { ...q, graphic: { ...q.graphic, state: "on_air" } } } : s.graphics };
    }
    case "program_clear":
      return s.program ? { ...s, program: null } : s;
    case "event":
      return msg.event ? { ...s, events: applyEvent(s.events, msg.event) } : s;
    default:
      return s; // "latency" y desconocidos
  }
}

/** Reductor puro: toda la entrada (mensajes, reloj) llega en la acción; no lee Date.now(). */
export function reducer(s: LiveState, a: LiveAction): LiveState {
  switch (a.type) {
    case "conn":
      return s.connected === a.connected ? s : { ...s, connected: a.connected, everConnected: s.everConnected || a.connected };
    case "msg":
      return onMsg(s, a.msg, a.now);
    case "snapshot": {
      const d = a.data;
      let next = s;
      if (d.state) next = { ...next, match: d.state };
      if (d.events) next = { ...next, events: [...d.events].sort(byTime) };
      for (const g of d.graphics ?? []) if (!next.graphics[g.id]) next = putGraphic(next, g, a.now);
      // putGraphic antepone: la lista llega de más antiguo a más nuevo, así que el último queda arriba
      // d.program se ignora a propósito: no trae server_now y el servidor ya reenvía el grafismo en antena en el "hello",
      // con edad calculable (ver "program"); usarlo aquí resucitaría grafismos vencidos.
      return next;
    }
    case "tick": {
      const onAir = s.program?.graphic.id;
      const dead = s.order.filter((id) => isExpired(s.graphics[id], a.now, id === onAir));
      if (!dead.length) return s;
      const graphics = { ...s.graphics };
      for (const id of dead) delete graphics[id];
      return { ...s, graphics, order: s.order.filter((id) => !dead.includes(id)) };
    }
    case "program_expire":
      return s.program && s.program.graphic.id === a.id ? { ...s, program: null } : s;
  }
}
