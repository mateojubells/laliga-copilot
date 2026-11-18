import { useCallback, useEffect, useReducer, useRef } from "react";
import { LiveClient, type LiveClientOptions } from "./client";
import { initialState, reducer } from "./reducer";
import type { OperatorAction, Role, Snapshot } from "./types";

export interface UseLiveOptions {
  /** Para tests: construir el cliente con otro WebSocket / URL. */
  client?: Partial<LiveClientOptions>;
  /** Cargar GET /api/state al (re)conectar. Por defecto, sólo en el operador. */
  snapshot?: boolean;
}

/** Estado en vivo + envío de acciones. role="operator" | "program". */
export function useLive(role: Role, opts: UseLiveOptions = {}) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const clientRef = useRef<LiveClient | null>(null);
  const wantSnapshot = opts.snapshot ?? role === "operator";
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    let alive = true;
    const loadSnapshot = () => {
      if (!wantSnapshot || typeof fetch !== "function") return;
      fetch("/api/state")
        .then((r) => (r.ok ? (r.json() as Promise<Snapshot>) : null))
        .then((d) => { if (alive && d) dispatch({ type: "snapshot", data: d, now: Date.now() }); })
        .catch(() => { /* sin backend: se queda vacío */ });
    };
    const client = new LiveClient({
      role,
      ...optsRef.current.client,
      onMessage: (msg) => dispatch({ type: "msg", msg, now: Date.now() }),
      onConnection: (connected) => {
        dispatch({ type: "conn", connected });
        if (connected) loadSnapshot();
      },
    });
    clientRef.current = client;
    client.start();
    const tick = setInterval(() => dispatch({ type: "tick", now: Date.now() }), 1000);
    return () => {
      alive = false;
      clearInterval(tick);
      client.stop();
      clientRef.current = null;
    };
  }, [role, wantSnapshot]);

  // Caducidad del grafismo en antena: si no está fijado, se retira al vencer su ttl.
  const prog = state.program;
  useEffect(() => {
    if (!prog || prog.graphic.pinned) return;
    const left = prog.since + (prog.graphic.ttl_ms ?? 12000) - Date.now();
    const id = prog.graphic.id;
    const t = setTimeout(() => dispatch({ type: "program_expire", id }), Math.max(0, left));
    return () => clearTimeout(t);
  }, [prog]);

  const send = useCallback((a: OperatorAction) => clientRef.current?.send(a) ?? false, []);

  /** Avisa al servidor de que el grafismo ya está en pantalla (latencia de pintado). */
  const reportPainted = useCallback((graphicId: string) => {
    const c = clientRef.current;
    if (!c) return;
    c.send({ type: "painted", graphic_id: graphicId, t_paint: c.serverNow() });
  }, []);

  return { state, send, reportPainted, clientRef };
}

/** Tras montarse el grafismo, en el segundo requestAnimationFrame, llama a `cb`. */
export function usePaintedCallback(graphicId: string | null | undefined, cb: (id: string) => void) {
  const cbRef = useRef(cb);
  cbRef.current = cb;
  useEffect(() => {
    if (!graphicId) return;
    let r2 = 0;
    const r1 = requestAnimationFrame(() => { r2 = requestAnimationFrame(() => cbRef.current(graphicId)); });
    return () => { cancelAnimationFrame(r1); cancelAnimationFrame(r2); };
  }, [graphicId]);
}
