import { AnimatePresence } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { Graphic, MatchState } from "../contracts";
import { CANVAS_H, CANVAS_W } from "../design";
import { GraphicView } from "../graphics/GraphicFrame";
import { usePaintedCallback, useLive } from "../live";
import "./Program.css";

/** MatchState → grafismo scorebug (marcador permanente). */
export function scorebugOf(m: MatchState): Pick<Graphic, "payload" | "demo_data"> {
  return {
    demo_data: false,
    payload: {
      kind: "scorebug",
      home: m.home,
      away: m.away,
      home_goals: m.home_goals ?? 0,
      away_goals: m.away_goals ?? 0,
      minute: m.minute ?? null,
      period: m.period ?? 0,
    },
  };
}

/** Escala para que 1920×1080 quepa en la ventana sin deformarse. */
export function fitScale(w: number, h: number): number {
  return Math.min(w / CANVAS_W, h / CANVAS_H);
}

function useFitScale(fixed: boolean): number {
  const get = () => (fixed ? 1 : fitScale(window.innerWidth, window.innerHeight));
  const [s, setS] = useState(get);
  useEffect(() => {
    if (fixed) return setS(1);
    const on = () => setS(get());
    on();
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fixed]);
  return s;
}

/**
 * Salida de programa para OBS: 1920×1080, fondo transparente, sin controles ni errores en pantalla.
 * Parámetros: ?scale=1 (sin escalar), ?scorebug=0 (sin marcador), ?bg=green (croma de prueba).
 * Pinta SOLO lo que llega por "program"; se retira con "program_clear" o al vencer su ttl_ms (si no está fijado).
 */
export function Program() {
  const [params] = useSearchParams();
  const scale = useFitScale(params.get("scale") === "1");
  const showScorebug = params.get("scorebug") !== "0";
  const bg = params.get("bg");
  const { state, reportPainted } = useLive("program");

  useEffect(() => {
    document.body.classList.add("program");
    document.documentElement.classList.add("program-page");
    return () => {
      document.body.classList.remove("program");
      document.documentElement.classList.remove("program-page");
    };
  }, []);

  const g = state.program?.graphic ?? null;
  usePaintedCallback(g?.id, reportPainted);
  const bug = useMemo(() => (state.match ? scorebugOf(state.match) : null), [state.match]);
  const bugVisible = showScorebug && bug && g?.payload.kind !== "scorebug";

  return (
    <div className="prog-root" data-bg={bg ?? undefined} data-testid="program-root">
      <div className="prog-canvas" data-testid="program-canvas" style={{ transform: `scale(${scale})` }}>
        {bugVisible && <GraphicView graphic={bug} />}
        <AnimatePresence>{g && <GraphicView key={g.id} graphic={g} />}</AnimatePresence>
      </div>
    </div>
  );
}
