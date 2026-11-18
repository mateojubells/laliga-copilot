import type { CSSProperties } from "react";
import { StatTile, accentOn, edgeOn, inkOn } from "../design";
import type { Arrow } from "../contracts";
import { ARROW_STYLE, ArrowsLayer, AttackArrow, NodesLayer, Pitch, fitView, usePitch, type ArrowDatum, type NodeDatum } from "../pitch";
import "./Connection.css";
import { FIELD_PAD, FIELD_TOP_BAND, FieldShell, Reveal, fmtInt, surname } from "./shared";
import type { GraphicProps } from "./types";

/** Campo de 560 px: con el encuadre a la zona de la jugada sale a ≈ 9-10 px/m (antes 6,9). */
const PITCH_W = 560;
const MIN_K = 9;

const LEGEND: { kind: NonNullable<Arrow["kind"]>; label: string }[] = [
  { kind: "pass", label: "Pase" },
  { kind: "key_pass", label: "Pase clave" },
  { kind: "assist", label: "Asistencia" },
];

/** "18 últimos pases": el pie del campo (no es un tipo de flecha), en la banda superior a la derecha de "ATAQUE →". */
function SampleNote({ text }: { text: string }) {
  const { width, top } = usePitch();
  return (
    <text x={width - 4} y={top / 2} dy="0.34em" textAnchor="end" fontFamily="var(--font-text)" fontWeight={500} fontSize={24} fill="var(--c-text-2)" data-testid="cn-sample">
      {text}
    </text>
  );
}

/** Conexión entre dos jugadores: cifras A→B / B→A, pases clave, asistencias y las flechas de la muestra. */
export function Connection({ payload, demoData }: GraphicProps<"connection">) {
  const { a, b, scope, headline, arrows, a_pos, b_pos } = payload;
  const accent = accentOn(a.team.colors.primary ?? "#7cc4ff");
  // dos nombres largos no caben en dos líneas de 44 px: se pasa a los apellidos
  const title = a.known_as.length + b.known_as.length > 34 ? `${surname(a)} ↔ ${surname(b)}` : `${a.known_as} ↔ ${b.known_as}`;
  const labAB = `Pases ${surname(a)} → ${surname(b)}`;
  const labBA = `Pases ${surname(b)} → ${surname(a)}`;
  const longLabel = Math.max(labAB.length, labBA.length) > 19; // a 24 px caben ~19 caracteres en media columna: pasa a dos líneas
  // colores REALES: el del club para A y el secundario (o blanco) para B; las cifras van en blanco y el color, en el filete
  const fillA = a.team.colors.primary ?? "#445";
  const fillB = b.team.colors.secondary && b.team.colors.secondary !== fillA ? b.team.colors.secondary : "#ffffff";
  const nodes: NodeDatum[] = [
    { id: a.id, x: a_pos[0], y: a_pos[1], number: a.number, label: surname(a), size: 80, fill: fillA, textColor: inkOn(fillA) },
    // receptor sólido (100 %) y pintado DESPUÉS de las flechas: las puntas que llegan a su aro quedan debajo de él
    { id: b.id, x: b_pos[0], y: b_pos[1], number: b.number, label: surname(b), size: 80, fill: fillB, textColor: inkOn(fillB) },
  ];
  // paleta única de flechas: pase blanco al 45 %, pase clave blanco pleno, asistencia dorada (ARROW_STYLE)
  const data: ArrowDatum[] = arrows.map((ar) => ({ ...ar }));
  // encuadre a la jugada: caja de los dos jugadores y de todas las flechas (+ 6 m), recortada para no bajar de MIN_K px/m
  const pts = [a_pos, b_pos, ...arrows.flatMap((ar) => [[ar.x, ar.y] as [number, number], [ar.end_x, ar.end_y] as [number, number]])];
  const view = fitView(pts, {
    width: PITCH_W, padding: FIELD_PAD, margin: 6, minK: MIN_K, minPlotH: 420, maxPlotH: 480,
    fallback: { x0: 36, x1: 96, y0: 0, y1: 44 },
  });
  return (
    <FieldShell
      kicker="Conexión"
      title={title}
      headline={headline}
      team={a.team}
      scope={scope.label}
      demoData={demoData}
      pitchW={PITCH_W}
      className="cn"
      pitch={
        <Pitch view={view} width={PITCH_W} padding={FIELD_PAD} topBand={FIELD_TOP_BAND} accent={accent} label={`Pases de ${a.known_as} a ${b.known_as}`}>
          <ArrowsLayer arrows={data} endDots />
          <NodesLayer nodes={nodes} avoid={data} />
          <AttackArrow />
          {arrows.length > 0 && <SampleNote text={`${arrows.length} últimos pases`} />}
        </Pitch>
      }
      side={
        <>
          <Reveal className={`cn__figs${longLabel ? " cn__figs--long" : ""}`}>
            <div className="cn__fig" style={{ "--c": edgeOn(fillA) } as CSSProperties}>
              <span className="cn__fig-l">{labAB}</span>
              <b className="cn__fig-v display num" data-testid="cn-ab">{fmtInt(payload.a_to_b)}</b>
            </div>
            <div className="cn__fig" style={{ "--c": edgeOn(fillB) } as CSSProperties}>
              <span className="cn__fig-l">{labBA}</span>
              <b className="cn__fig-v display num" data-testid="cn-ba">{fmtInt(payload.b_to_a)}</b>
            </div>
          </Reveal>
          <Reveal className="sd__tiles cn__tiles">
            <StatTile label="Pases clave" value={String(payload.key_passes)} edge={ARROW_STYLE.key_pass.color} />
            <StatTile label="Asistencias" value={String(payload.assists)} edge={ARROW_STYLE.assist.color} />
          </Reveal>
          <Reveal className="cn__legend" data-testid="cn-legend">
            {LEGEND.map((l) => {
              const st = ARROW_STYLE[l.kind];
              return (
                <span key={l.kind}><i style={{ background: st.color, opacity: st.opacity, height: st.width }} />{l.label}</span>
              );
            })}
          </Reveal>
        </>
      }
    />
  );
}
