import { describe, expect, it } from "vitest";
import type { Graphic, ServerMsg } from "../contracts";
import { FIXTURES } from "../fixtures";
import { backoffDelay } from "./client";
import { ClockSync, estimateOffset } from "./clock";
import { EXPIRE_MS, STALE_MS, isExpired, isStale, protagonists } from "./queue";
import { initialState, reducer } from "./reducer";
import type { LiveAction, LiveState, MatchEvent } from "./types";

const g = (id: string, extra: Partial<Graphic> = {}): Graphic => ({ id, kind: "player_card", priority: 70, ttl_ms: 12000, payload: FIXTURES.player_card, ...extra });
const msg = (m: Partial<ServerMsg> & Pick<ServerMsg, "type">, now = 1000): LiveAction => ({ type: "msg", msg: { server_now: 0, ...m } as ServerMsg, now });
const run = (actions: LiveAction[], s: LiveState = initialState()) => actions.reduce(reducer, s);
const ev = (id: string, t: number, extra: Partial<MatchEvent> = {}): Record<string, unknown> => ({ id, t_audio: t, type: "gol", roles: {}, status: "auto", ...extra });

describe("reducer", () => {
  it("graphic: añade a la cola con el más nuevo arriba y conserva la hora de llegada al actualizar", () => {
    let s = run([msg({ type: "graphic", graphic: g("a") }, 100), msg({ type: "graphic", graphic: g("b") }, 200)]);
    expect(s.order).toEqual(["b", "a"]);
    s = run([msg({ type: "graphic", graphic: g("a", { pinned: true }) }, 900)], s);
    expect(s.order).toEqual(["b", "a"]);
    expect(s.graphics.a.receivedAt).toBe(100);
    expect(s.graphics.a.graphic.pinned).toBe(true);
  });

  it("graphic con state on_air se marca como auto", () => {
    const s = run([msg({ type: "graphic", graphic: g("a", { state: "on_air" }) })]);
    expect(s.graphics.a.auto).toBe(true);
  });

  it("graphic_hide la saca de la cola", () => {
    const s = run([msg({ type: "graphic", graphic: g("a") }), msg({ type: "graphic_hide", graphic_id: "a" })]);
    expect(s.order).toEqual([]);
    expect(s.graphics.a).toBeUndefined();
  });

  it("program pone el grafismo en antena y program_clear lo quita; la cola no se toca", () => {
    let s = run([msg({ type: "graphic", graphic: g("a") }), msg({ type: "program", graphic: g("a") }, 500)]);
    expect(s.program?.graphic.id).toBe("a");
    expect(s.program?.since).toBe(500);
    expect(s.graphics.a.graphic.state).toBe("on_air");
    s = run([msg({ type: "program_clear" })], s);
    expect(s.program).toBeNull();
    expect(s.order).toEqual(["a"]);
  });

  it("program reenviado al reconectar: ignora lo vencido y recorta el ttl de lo que queda", () => {
    const old = g("a", { ttl_ms: 12000, ts: { ws_send: 1000 } });
    expect(run([{ type: "msg", msg: { type: "program", server_now: 1000 + 13_000, graphic: old }, now: 50_000 }]).program).toBeNull();
    const s = run([{ type: "msg", msg: { type: "program", server_now: 1000 + 5_000, graphic: old }, now: 50_000 }]);
    expect(s.program?.since).toBe(45_000); // quedan 7 s
  });

  it("program_expire sólo retira el grafismo que sigue en antena", () => {
    const s = run([msg({ type: "program", graphic: g("a") })]);
    expect(reducer(s, { type: "program_expire", id: "otro" })).toBe(s);
    expect(reducer(s, { type: "program_expire", id: "a" }).program).toBeNull();
  });

  it("event: new, update, retract y reload", () => {
    let s = run([msg({ type: "event", event: { ...ev("e2", 20), action: "new" } }), msg({ type: "event", event: { ...ev("e1", 10), action: "new" } })]);
    expect(s.events.map((e) => e.id)).toEqual(["e1", "e2"]); // ordenados por tiempo de audio
    s = run([msg({ type: "event", event: { ...ev("e1", 10, { status: "approved" }), action: "update" } })], s);
    expect(s.events[0].status).toBe("approved");
    s = run([msg({ type: "event", event: { ...ev("e1", 10), action: "retract" } })], s);
    expect(s.events.map((e) => e.id)).toEqual(["e2"]);
    s = run([msg({ type: "event", event: { action: "reload", events: [ev("x", 5), ev("y", 1)] } })], s);
    expect(s.events.map((e) => e.id)).toEqual(["y", "x"]);
  });

  it("state y hello actualizan el marcador y el estado de motores", () => {
    const match = { ...FIXTURES.scorebug, match: "m" } as never;
    let s = run([msg({ type: "hello", state: match, data: { role: "operator", auto_program: true, status: { asr: "inactivo", data: "ok", errors: 0, replay: null } } })]);
    expect(s.match).toBe(match);
    expect(s.autoProgram).toBe(true);
    expect(s.status).toMatchObject({ asr: "inactivo", data: "ok", errors: 0 });
    s = run([msg({ type: "state", state: { ...(match as object), home_goals: 1 } as never })], s);
    expect(s.match?.home_goals).toBe(1);
  });

  it("status: replay_started dispara un contador y set_auto actualiza el interruptor", () => {
    let s = run([msg({ type: "status", data: { errors: 2, replay: { speed: 2 }, replay_started: { audio_t: 1185, speed: 2 } } })]);
    expect(s.replayStarted).toEqual({ audio_t: 1185, speed: 2, n: 1 });
    expect(s.status.errors).toBe(2);
    s = run([msg({ type: "status", data: { replay_started: { audio_t: 0, speed: 1 } } }), msg({ type: "status", data: { auto_program: false, replay: null } })], s);
    expect(s.replayStarted?.n).toBe(2);
    expect(s.autoProgram).toBe(false);
    expect(s.status.replay).toBeNull();
  });

  it("transcript: el parcial se reemplaza y el final lo sustituye y se acumula sin duplicar", () => {
    const tr = (final: boolean, text: string, id = "t1") => msg({ type: "transcript", transcript: { trace_id: id, final, text, t0: 61, t1: 63 } });
    let s = run([tr(false, "gol de"), tr(false, "gol de Lewan")]);
    expect(s.partial?.text).toBe("gol de Lewan");
    expect(s.finals).toHaveLength(0);
    s = run([tr(true, "gol de Lewandowski")], s);
    expect(s.partial).toBeNull();
    expect(s.finals.map((f) => f.text)).toEqual(["gol de Lewandowski"]);
    s = run([tr(true, "gol de Lewandowski")], s);
    expect(s.finals).toHaveLength(1);
  });

  it("snapshot carga eventos y grafismos (el último arriba) sin pisar lo ya recibido", () => {
    const s0 = run([msg({ type: "graphic", graphic: g("b") }, 10)]);
    const s = run([{ type: "snapshot", now: 50, data: { events: [ev("e1", 3) as unknown as MatchEvent], graphics: [g("a"), g("b"), g("c")], program: g("c") } }], s0);
    expect(s.order).toEqual(["c", "a", "b"].filter((x) => s.order.includes(x)));
    expect(s.graphics.b.receivedAt).toBe(10);
    expect(s.events).toHaveLength(1);
    expect(s.program).toBeNull(); // el programa llega por "hello"+"program", con edad
  });

  it("conn marca la conexión", () => {
    const s = run([{ type: "conn", connected: true }, { type: "conn", connected: false }]);
    expect(s.connected).toBe(false);
    expect(s.everConnected).toBe(true);
  });
});

describe("caducidad de la cola", () => {
  const item = (extra: Partial<Graphic> = {}) => ({ graphic: g("a", extra), receivedAt: 0, auto: false });
  it("se atenúa a los 60 s y expira a los 3 min, salvo si está fijada o en antena", () => {
    expect(isStale(item(), STALE_MS - 1)).toBe(false);
    expect(isStale(item(), STALE_MS)).toBe(true);
    expect(isExpired(item(), STALE_MS)).toBe(false);
    expect(isExpired(item(), EXPIRE_MS)).toBe(true);
    expect(isStale(item({ pinned: true }), EXPIRE_MS * 2)).toBe(false);
    expect(isExpired(item({ pinned: true }), EXPIRE_MS * 2)).toBe(false);
    expect(isExpired(item(), EXPIRE_MS * 2, true)).toBe(false);
  });

  it("tick elimina lo caducado, respeta fijadas y lo que está en antena, y no cambia el estado si no hay nada", () => {
    let s = run([
      msg({ type: "graphic", graphic: g("old") }, 0), msg({ type: "graphic", graphic: g("pin", { pinned: true }) }, 0),
      msg({ type: "graphic", graphic: g("air") }, 0), msg({ type: "graphic", graphic: g("new") }, EXPIRE_MS),
      msg({ type: "program", graphic: g("air") }, 0),
    ]);
    const same = reducer(s, { type: "tick", now: STALE_MS });
    expect(same).toBe(s);
    s = reducer(s, { type: "tick", now: EXPIRE_MS + 1 });
    expect(s.order.sort()).toEqual(["air", "new", "pin"]);
  });

  it("protagonists describe el grafismo", () => {
    expect(protagonists(g("a"))).toBe("Lamine Yamal");
  });
});

describe("reloj", () => {
  it("offset = server_now − (client_now + rtt/2)", () => {
    const s = estimateOffset(1000, 51_050, 1100);
    expect(s.rtt).toBe(100);
    expect(s.offset).toBe(51_050 - 1050);
  });
  it("ClockSync usa la muestra de menor RTT y convierte tiempos", () => {
    const c = new ClockSync(3);
    expect(c.ready).toBe(false);
    expect(c.offset).toBe(0);
    c.add(0, 10_000, 200); // rtt 200 → offset 9900
    c.add(1000, 11_010, 1020); // rtt 20 → offset 10000
    c.add(2000, 12_500, 2400); // rtt 400
    expect(c.best?.rtt).toBe(20);
    expect(c.offset).toBe(10_000);
    expect(c.serverTime(5)).toBe(10_005);
  });
});

describe("reconexión", () => {
  it("espera creciente con tope", () => {
    expect([0, 1, 2, 3, 4, 5, 9].map((n) => backoffDelay(n))).toEqual([500, 1000, 2000, 4000, 8000, 8000, 8000]);
  });
});
