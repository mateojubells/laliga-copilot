import { MotionGlobalConfig, processFrame } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { GraphicKind, Payload } from "../contracts";
import { GRAPHIC_KINDS } from "../contracts";
import { CANVAS_W, ImageSourceProvider, Stage, type ImageMode } from "../design";
import { EDGE_FIXTURES, FIXTURES, standingsTop } from "../fixtures";
import { GraphicView } from "../graphics/GraphicFrame";
import { STATUS } from "../graphics/registry";
import "./Gallery.css";

type Bg = "video" | "transparent" | "green";
const BGS: Bg[] = ["video", "transparent", "green"];

interface Entry {
  id: string;
  kind: GraphicKind;
  title: string;
  payload: Payload;
}

/** Casos normales (los del dossier) o límite (`?case=edge`: nombres largos, clubes claros/oscuros, ceros, listas vacías). */
const entriesFor = (edge: boolean): Entry[] =>
  GRAPHIC_KINDS.flatMap((kind): Entry[] => {
    const base: Entry = { id: kind, kind, title: edge ? `${kind} · caso límite` : kind, payload: (edge ? EDGE_FIXTURES : FIXTURES)[kind] };
    return kind === "standings"
      ? [
          { ...base, title: edge ? "standings · tabla completa · caso límite" : "standings · tabla completa" },
          { id: "standings_top", kind, title: edge ? "standings · top 8 · caso límite" : "standings · top 8", payload: edge ? { ...EDGE_FIXTURES.standings, rows: EDGE_FIXTURES.standings.rows.slice(0, 8), window: "top" } : standingsTop },
        ]
      : [base];
  });

const STATUS_LABEL = { done: "completo", draft: "borrador", pending: "pendiente" } as const;

/**
 * ?freeze=<ms>: detiene la animación de entrada en ese instante (para comprobar fotogramas sueltos sin grabar vídeo). Framer Motion
 * pasa a reloj manual y aquí se avanza a mano, en pasos de 8 ms, hasta `ms`; las animaciones CSS (barras de percentil) se
 * pausan en el mismo instante. Después de `ms` nada se mueve.
 */
function freezeAt(ms: number) {
  processFrame(0);
  for (let t = 8; t < ms; t += 8) processFrame(t);
  processFrame(ms);
  for (const a of document.getAnimations()) {
    a.pause();
    a.currentTime = ms;
  }
}

function Frame({ entry, bg, solo, size, bare, editorial, variant, freeze }: { entry: Entry; bg: Bg; solo: boolean; size: number | null; bare: boolean; editorial: boolean; variant?: string; freeze: number | null }) {
  const [run, setRun] = useState(0); // reinicia la animación de entrada
  useEffect(() => {
    if (freeze == null) return;
    const id = setTimeout(() => freezeAt(freeze), 60); // tras montar: los hijos ya han programado sus animaciones
    return () => clearTimeout(id);
  }, [freeze, run]);
  const status = STATUS[entry.kind];
  return (
    <figure className={`g-frame${solo ? " g-frame--solo" : ""}`} data-testid={`frame-${entry.id}`}>
      <figcaption hidden={bare}>
        <span className="display caps">{entry.title}</span>
        <span className={`g-tag g-tag--${status}`}>{STATUS_LABEL[status]}</span>
        <button type="button" onClick={() => setRun((n) => n + 1)}>Repetir animación</button>
      </figcaption>
      {size ? (
        // tamaño real: el lienzo lógico se pinta a `size` px de ancho SIN escalar al contenedor (capturas 1920×1080)
        <div style={{ width: size }} data-testid="stage-fixed">
          <Stage className={`g-bg g-bg--${bg}`} fixedScale={size / CANVAS_W}>
            <GraphicView key={run} graphic={{ payload: entry.payload, demo_data: true }} editorial={editorial} variant={variant} />
          </Stage>
        </div>
      ) : (
        <Stage className={`g-bg g-bg--${bg}`}>
          <GraphicView key={run} graphic={{ payload: entry.payload, demo_data: true }} editorial={editorial} variant={variant} />
        </Stage>
      )}
    </figure>
  );
}

/**
 * Galería de grafismos con datos de ejemplo. ?only=<kind> aísla uno; ?bg=video|transparent|green; ?img=remote usa /api/img;
 * ?static=1 desactiva las animaciones. ?case=edge pinta los casos límite (nombres largos, clubes claros y oscuros, ceros, listas vacías). ?freeze=<ms> detiene la animación de entrada en ese instante (fotogramas a 150 / 300 ms). ?editorial=1 pinta la vista de operador (por defecto, la de antena). ?size=1920&bare=1 quita la cabecera y los rótulos (el lienzo queda en 0,0). ?size=1920 muestra cada grafismo a tamaño real (1920×1080 sin escalar, para capturas) en lugar de la rejilla.
 */
export function Gallery() {
  const [params] = useSearchParams();
  const only = params.get("only");
  const bgParam = params.get("bg");
  const bg: Bg = BGS.includes(bgParam as Bg) ? (bgParam as Bg) : "video";
  const mode: ImageMode = params.get("img") === "remote" ? "remote" : "generated";
  const sizeParam = Number(params.get("size"));
  const size = Number.isFinite(sizeParam) && sizeParam >= 320 ? Math.round(sizeParam) : null;
  // ?static=1: sin animaciones (las capturas salen en el estado final)
  const freezeParam = params.get("freeze");
  const freeze = freezeParam != null && freezeParam !== "" && Number.isFinite(Number(freezeParam)) ? Math.max(0, Number(freezeParam)) : null;
  MotionGlobalConfig.skipAnimations = params.get("static") === "1" && freeze == null;
  MotionGlobalConfig.useManualTiming = freeze != null; // ?freeze: reloj manual (ver freezeAt)
  const edge = params.get("case") === "edge";
  const entries = entriesFor(edge);
  // ?editorial=1: vista de operador (estados de moderación visibles); ?variant=full|live: variante de formato (h2h)
  const editorial = params.get("editorial") === "1";
  const variant = params.get("variant") ?? undefined;
  const bare = params.get("bare") === "1" && !!size; // sólo el lienzo, sin cabecera ni rótulos (capturas)
  const shown = only ? entries.filter((e) => e.kind === only || e.id === only) : entries;
  const q = (extra: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(extra)) v == null ? p.delete(k) : p.set(k, v);
    const s = p.toString();
    return s ? `?${s}` : "";
  };
  return (
    <ImageSourceProvider mode={mode}>
      <main className={`g-page${bare ? " g-page--bare" : ""}`}>
        <header className="g-top" hidden={bare}>
          <h1 className="display caps">Galería de grafismos</h1>
          <nav aria-label="Filtro por grafismo">
            <Link to={q({ only: null })} className={!only ? "on" : ""}>todos</Link>
            {GRAPHIC_KINDS.map((k) => (
              <Link key={k} to={q({ only: k })} className={only === k ? "on" : ""}>{k}</Link>
            ))}
          </nav>
          <nav aria-label="Tamaño">
            vista:
            <Link to={q({ size: null })} className={!size ? "on" : ""}>rejilla</Link>
            <Link to={q({ size: "1920" })} className={size === 1920 ? "on" : ""}>1920×1080</Link>
          </nav>
          <nav aria-label="Caso">
            caso:
            <Link to={q({ case: null })} className={!edge ? "on" : ""}>normal</Link>
            <Link to={q({ case: "edge" })} className={edge ? "on" : ""}>límite</Link>
          </nav>
          <nav aria-label="Fondo">
            fondo:
            {BGS.map((b) => (
              <Link key={b} to={q({ bg: b })} className={bg === b ? "on" : ""}>{b}</Link>
            ))}
          </nav>
        </header>
        <div className={`g-grid${only ? " g-grid--solo" : ""}${size ? " g-grid--size" : ""}`}>
          {shown.map((e) => (
            <Frame key={e.id} entry={e} bg={bg} solo={!!only} size={size} bare={bare} editorial={editorial} variant={variant} freeze={freeze} />
          ))}
        </div>
      </main>
    </ImageSourceProvider>
  );
}
