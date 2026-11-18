import { accentOn, inkOn } from "../design";
import type { NetNode } from "../contracts";
import { ARROW_COUNT_OPACITY, ArrowsLayer, AttackArrow, NodesLayer, Pitch, arrowWidth, nodeRadiusScale, usePitch, type ArrowDatum, type NodeDatum } from "../pitch";
import "./PassNetwork.css";
import { FIELD_PAD, FIELD_TOP_BAND, FieldShell, Reveal, surname } from "./shared";
import type { GraphicProps } from "./types";

const PITCH_W = 990;

/** Aristas que superan el mínimo de pases, con sus extremos resueltos. */
export function visibleEdges(payload: GraphicProps<"pass_network">["payload"]) {
  const by = new Map(payload.nodes.map((n) => [n.player.id, n]));
  return payload.edges.flatMap((e) => {
    const a = by.get(e.a);
    const b = by.get(e.b);
    return a && b && e.count >= payload.min_passes ? [{ ...e, from: a, to: b }] : [];
  });
}

/** Por debajo de este recuento una flecha menor se dibuja sin punta (menos ruido en el centro del campo). */
const HEAD_FROM = 14;

/**
 * Flechas de la red: los pares de ida y vuelta se funden en UNA línea sin punta con el grosor de la suma; la conexión
 * destacada conserva su sentido (con punta); las demás de menos de 14 pases van sin punta. Devuelve también el dominio de
 * grosor (umbral y máximo) para que la leyenda dibuje los mismos trazos.
 */
export function networkArrows(payload: GraphicProps<"pass_network">["payload"], r: (passes: number) => number) {
  const edges = visibleEdges(payload);
  const has = new Set(edges.map((e) => `${e.a}>${e.b}`));
  const arrows: ArrowDatum[] = [];
  for (const e of edges) {
    const rev = has.has(`${e.b}>${e.a}`);
    const other = rev ? edges.find((x) => x.a === e.b && x.b === e.a) : undefined;
    const fuse = rev && !e.highlight && !other?.highlight;
    if (fuse && e.a > e.b) continue; // el par se pinta una sola vez
    const count = fuse ? e.count + (other?.count ?? 0) : e.count;
    arrows.push({
      x: e.from.x, y: e.from.y, end_x: e.to.x, end_y: e.to.y, count, highlight: e.highlight,
      offset: rev && !fuse ? 7 : 0,
      noHead: fuse || (!e.highlight && e.count < HEAD_FROM),
      gapStart: r(e.from.passes) + 4,
      gapEnd: r(e.to.passes) + (fuse || (!e.highlight && e.count < HEAD_FROM) ? 4 : 7),
    });
  }
  const counts = arrows.map((a) => a.count!);
  return { arrows, lo: payload.min_passes, hi: Math.max(payload.min_passes + 1, ...counts) };
}

function NetworkLayers({ payload }: { payload: GraphicProps<"pass_network">["payload"] }) {
  const { k } = usePitch();
  const r = nodeRadiusScale(payload.nodes.map((n) => n.passes), k);
  const { arrows } = networkArrows(payload, r);
  const nodes: NodeDatum[] = payload.nodes.map((n) => {
    const c = n.player.team.colors.primary ?? "#445";
    return {
      id: n.player.id, x: n.x, y: n.y, number: n.player.number, label: surname(n.player), size: n.passes,
      fill: c, textColor: inkOn(c), highlight: n.highlight,
    };
  });
  return (
    <>
      <ArrowsLayer arrows={arrows} minCount={payload.min_passes} opacity={ARROW_COUNT_OPACITY} highlightColor={payload.team.colors.primary} />
      <NodesLayer nodes={nodes} avoid={arrows} />
      <AttackArrow />
    </>
  );
}

function topEdges(payload: GraphicProps<"pass_network">["payload"], n: number) {
  const nameOf = new Map<string, NetNode>(payload.nodes.map((x) => [x.player.id, x]));
  return visibleEdges(payload)
    .sort((a, b) => b.count - a.count)
    .slice(0, n)
    .map((e) => ({ ...e, a: nameOf.get(e.a)!, b: nameOf.get(e.b)! }));
}

/** Red de pases (pantalla completa, para repetición o descanso): 11 nodos en su posición media (tamaño ∝ pases), aristas ∝ pases entre pares (≥ min_passes). */
export function PassNetwork({ payload, demoData }: GraphicProps<"pass_network">) {
  const { team, scope, headline, min_passes: min } = payload;
  const edges = visibleEdges(payload);
  const top = topEdges(payload, 5);
  // la leyenda usa el mismo dominio de grosor que el campo (los pares fundidos suman)
  const { hi: max } = networkArrows(payload, () => 0);
  const samples = Array.from(new Set([min, Math.round((min + max) / 2), max])).filter((v) => v >= 1);
  const anyHl = edges.some((e) => e.highlight);
  return (
    <FieldShell
      kicker="Red de pases"
      title={team.name}
      headline={headline}
      team={team}
      scope={scope.label}
      demoData={demoData}
      pitchW={PITCH_W}
      format="full"
      className="pn"
      pitch={
        <Pitch width={PITCH_W} padding={FIELD_PAD} topBand={FIELD_TOP_BAND} accent={accentOn(team.colors.primary ?? "#7cc4ff")} label={`Red de pases de ${team.name}`}>
          <NetworkLayers payload={payload} />
        </Pitch>
      }
      side={
        <>
          <Reveal className="pn__top">
            <div className="sd__label">Conexiones más fuertes</div>
            {top.length === 0 && <p className="pn__empty" data-testid="pn-empty">Ninguna pareja llega a {min} pases</p>}
            <ol className="pn__list" data-testid="pn-top">
              {top.map((e) => (
                <li key={`${e.a.player.id}-${e.b.player.id}`} className={e.highlight ? "pn__li pn__li--hl" : "pn__li"}>
                  <span className="pn__pair">
                    {surname(e.a.player)} <i aria-hidden="true">→</i> {surname(e.b.player)}
                  </span>
                  <b className="pn__n display num">{e.count}</b>
                </li>
              ))}
            </ol>
          </Reveal>
          {edges.length > 0 && <Reveal className="pn__legend">
            <div className="sd__label">Grosor = pases entre los dos</div>
            <div className="lg" data-testid="pn-legend">
              {samples.map((v) => (
                <div className="lg__row" key={v}>
                  <i className="lg__line" style={{ height: arrowWidth(v, max, min), opacity: ARROW_COUNT_OPACITY }} />
                  {v} pases
                </div>
              ))}
              {anyHl && (
                <div className="lg__row" data-testid="pn-legend-hl">
                  <i className="lg__line lg__line--hl" />
                  Conexión destacada
                </div>
              )}
            </div>
          </Reveal>}
        </>
      }
    />
  );
}
