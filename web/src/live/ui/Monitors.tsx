import { AnimatePresence } from "framer-motion";
import { useMemo } from "react";
import { Stage } from "../../design";
import { GraphicView } from "../../graphics/GraphicFrame";
import { scorebugOf } from "../../routes/Program";
import { KIND_LABEL, protagonists } from "../queue";
import { usePaintedCallback } from "../useLive";
import type { Graphic, LiveState } from "../types";

function Video({ children }: { children: React.ReactNode }) {
  return (
    <Stage className="op-video">
      <div className="op-video__pitch" aria-hidden />
      {children}
    </Stage>
  );
}

/** Lo que está en antena ahora (réplica de /program) y la previa del grafismo seleccionado. */
export function Monitors({
  state, preview, onClear, reportPainted,
}: {
  state: LiveState;
  preview: Graphic | null;
  onClear: () => void;
  reportPainted: (id: string) => void;
}) {
  const live = state.program?.graphic ?? null;
  usePaintedCallback(live?.id, reportPainted);
  const bug = useMemo(() => (state.match ? scorebugOf(state.match) : null), [state.match]);
  return (
    <section className="op-col op-center" aria-label="Vista previa y programa">
      <div className="op-mon">
        <header>
          <h2><span className={`op-tally ${live ? "red" : ""}`} /> Programa</h2>
          <span className="op-dim op-ellipsis" data-testid="program-label">{live ? `${KIND_LABEL[live.kind] ?? live.kind} · ${protagonists(live)}` : "vacío"}</span>
          <button type="button" className="op-btn sm danger" disabled={!live} onClick={onClear}>Quitar <kbd>Esc</kbd></button>
        </header>
        <div className="op-mon__screen" data-testid="monitor-program">
          <Video>
            {bug && live?.payload.kind !== "scorebug" && <GraphicView graphic={bug} />}
            <AnimatePresence>{live && <GraphicView key={live.id} graphic={live} />}</AnimatePresence>
          </Video>
        </div>
      </div>
      <div className="op-mon">
        <header>
          <h2><span className="op-tally green" /> Previa</h2>
          <span className="op-dim op-ellipsis" data-testid="preview-label">{preview ? `${KIND_LABEL[preview.kind] ?? preview.kind} · ${protagonists(preview)}` : "selecciona una propuesta"}</span>
        </header>
        <div className="op-mon__screen" data-testid="monitor-preview">
          <Video>
            {bug && <GraphicView graphic={bug} />}
            <AnimatePresence mode="wait">{preview && <GraphicView key={preview.id} graphic={preview} />}</AnimatePresence>
          </Video>
        </div>
      </div>
    </section>
  );
}
