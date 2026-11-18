import { useCallback, useEffect, useRef, useState } from "react";
import type { SessionInfo } from "../contracts";
import { api } from "./api";

export type GuardState =
  | { status: "loading" }
  | { status: "none" }
  | { status: "active"; info: SessionInfo }
  | { status: "error"; message: string };

/**
 * Pregunta GET /api/session. Sin partido en curso (config null) → "none" (el operador redirige a /setup).
 * Si el servidor no responde se queda en "error" y reintenta cada `retryMs`; el operador sigue visible con un aviso.
 */
export function useSessionGuard(retryMs = 3000): GuardState {
  const [g, setG] = useState<GuardState>({ status: "loading" });
  const alive = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const load = useCallback(() => {
    api.session()
      .then((info) => { if (alive.current) setG(info.config ? { status: "active", info } : { status: "none" }); })
      .catch((e: Error) => {
        if (!alive.current) return;
        setG({ status: "error", message: e.message });
        timer.current = setTimeout(load, retryMs);
      });
  }, [retryMs]);

  useEffect(() => {
    alive.current = true;
    load();
    return () => { alive.current = false; clearTimeout(timer.current); };
  }, [load]);

  return g;
}
