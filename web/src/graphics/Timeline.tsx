import { motion } from "framer-motion";
import type { CSSProperties } from "react";
import type { TimelineItem } from "../contracts";
import { DemoBadge, Panel, TeamCrest, growVariants, pairAccents, popVariants } from "../design";
import { EventIcon, eventKind, EVENT_NAME, type EventKind } from "./EventIcon";
import { surname } from "./shared";
import "./Timeline.css";
import type { GraphicProps } from "./types";

export const TL_W = 1792;
/** Ancho útil del panel: 1792 − franja 16 − relleno 24 − relleno 32. */
const CONTENT_W = TL_W - 16 - 24 - 32;
const GUTTER = 200;
export const AXIS_W = CONTENT_W - GUTTER - 24;
const ICON = 48; // vista de operador: eventos menores
const ICON_MAJOR = 56; // vista de operador: eventos mayores; en antena todos son de 56
const GAP = 10; // hueco mínimo entre iconos vecinos
const CHAR_W = 13; // ancho medio de un carácter a 28 px en Barlow Condensed semibold
const STEM = 6; // alto del tallo entre el eje y el icono
const LABEL_H = 28;

/**
 * En antena solo goles, tarjetas y cambios: lo que el espectador entiende a 3 m. Lo demás es detalle de operador. El penalti
 * no va aparte: sale como el gol que provoca (un glifo de cuadrado con punto no se identifica a 3 m).
 */
export const AIR_KINDS: readonly EventKind[] = ["gol", "amarilla", "roja", "cambio"];
/** Estados que pueden salir en antena: un evento sin confirmar ("auto") o descartado no se pinta nunca fuera de la vista de operador. */
export const AIR_STATUS: readonly NonNullable<TimelineItem["status"]>[] = ["approved", "edited"];

export interface Placed {
  item: TimelineItem;
  minute: number;
  /** x real del minuto dentro del eje (px). */
  trueX: number;
  /** centro del icono tras separar los vecinos (px). */
  x: number;
  /** ancho del bloque = ancho del icono (px). */
  w: number;
  icon: number;
  /** Etiqueta (minuto + nombre) o null si el evento va sin etiqueta. */
  text: string | null;
  /** Fila de etiqueta (0 = pegada al icono, 1 = la de encima). */
  tier: number;
  /** Centro de la etiqueta respecto al icono (px), para que no se salga del eje. */
  shift: number;
  /** "center" = centrada en el icono; "end" / "start" = dos eventos próximos en una fila: la de la izquierda termina en el centro de su icono y la de la derecha empieza en el del suyo. */
  align: "center" | "end" | "start";
}

/** Texto bajo el icono: minuto y apellido (o el último tramo de la etiqueta). */
export function itemText(it: TimelineItem): string {
  const m = `${it.minute}'`;
  const who = it.players?.[0] ? surname(it.players[0]) : it.label.split("·").pop()!.trim();
  return `${m} ${who}`;
}

/**
 * Coloca los eventos de un lado en UNA fila de iconos: cada icono quiere estar en su minuto; los que se pisan se agrupan
 * y el grupo se reparte alrededor de su centro de gravedad (un tallo une cada icono con su minuto; el desplazamiento
 * típico es de un icono, ±32 px, porque las etiquetas NO empujan a los iconos). Las etiquetas (minuto + nombre) van
 * centradas en su icono y, si chocan con la anterior, suben a una segunda fila. Puro y testeable: sin solapes de iconos,
 * mismo orden temporal, dentro del eje. `labelAll` = todos llevan etiqueta (antena); si no, solo los `major`.
 */
export function layoutSide(items: readonly TimelineItem[], pxPerMin: number, axisW = AXIS_W, labelAll = false, uniformIcon = false): Placed[] {
  const base = items
    .filter((i) => i.minute != null)
    .sort((a, b) => a.minute! - b.minute!)
    .map((item): Placed => {
      const icon = uniformIcon || item.major ? ICON_MAJOR : ICON;
      const trueX = item.minute! * pxPerMin;
      return { item, minute: item.minute!, trueX, x: trueX, w: icon, icon, text: labelAll || item.major ? itemText(item) : null, tier: 0, shift: 0, align: "center" };
    });
  type Cluster = { members: Placed[]; left: number; width: number };
  const widthOf = (m: Placed[]) => m.reduce((s, p) => s + p.w, 0) + GAP * (m.length - 1);
  const leftOf = (m: Placed[]) => {
    let off = 0;
    let sum = 0;
    for (const p of m) {
      sum += p.trueX - off - p.w / 2; // posición ideal del borde izquierdo del grupo según este miembro
      off += p.w + GAP;
    }
    return sum / m.length;
  };
  const clamp = (c: Cluster) => ({ ...c, left: Math.min(Math.max(0, c.left), Math.max(0, axisW - c.width)) });
  let clusters: Cluster[] = base.map((p) => clamp({ members: [p], left: leftOf([p]), width: p.w }));
  for (let changed = true; changed; ) {
    changed = false;
    for (let i = 0; i < clusters.length - 1; i++) {
      const a = clusters[i]!;
      const b = clusters[i + 1]!;
      if (a.left + a.width + GAP > b.left + 0.01) {
        const members = [...a.members, ...b.members];
        clusters = [...clusters.slice(0, i), clamp({ members, left: leftOf(members), width: widthOf(members) }), ...clusters.slice(i + 2)];
        changed = true;
        break;
      }
    }
  }
  const placed = clusters.flatMap((c) => {
    let off = c.left;
    return c.members.map((p) => {
      const x = off + p.w / 2;
      off += p.w + GAP;
      return { ...p, x };
    });
  });
  // etiquetas: centradas en su icono (sin salirse del eje). Si chocan con la anterior de su fila, primero se prueba la
  // pareja (la anterior termina en el centro de su icono y esta empieza en el suyo, misma fila); si aun así no caben,
  // la etiqueta sube a la fila de encima.
  const span = (p: Placed, align: Placed["align"]): [number, number] => {
    const lw = p.text!.length * CHAR_W;
    const want = align === "end" ? p.x - lw / 2 : align === "start" ? p.x + lw / 2 : p.x;
    const cx = Math.min(Math.max(want, lw / 2), axisW - lw / 2);
    return [cx - lw / 2, cx + lw / 2];
  };
  const row0: Placed[] = [];
  for (const p of placed) {
    if (!p.text) continue;
    const prev = row0[row0.length - 1];
    const before = row0[row0.length - 2];
    const clear = (q: Placed | undefined, qa: Placed["align"], pa: Placed["align"]) => !q || span(q, qa)[1] + 8 <= span(p, pa)[0];
    if (clear(prev, prev?.align ?? "center", "center")) {
      p.align = "center";
      p.tier = 0;
      row0.push(p);
    } else if (prev && prev.align === "center" && clear(prev, "end", "start") && (!before || span(before, before.align)[1] + 8 <= span(prev, "end")[0])) {
      prev.align = "end";
      p.align = "start";
      p.tier = 0;
      row0.push(p);
    } else {
      p.tier = 1;
    }
  }
  for (const p of placed) if (p.text) p.shift = (span(p, p.align)[0] + span(p, p.align)[1]) / 2 - p.x;
  return placed;
}

/** Marcador a partir de los goles del propio listado (los descartados no cuentan). null si no hay ningún gol. */
export function scoreOf(items: readonly TimelineItem[], homeId: string, awayId: string): [number, number] | null {
  const goals = items.filter((i) => i.status !== "discarded" && eventKind(i.type) === "gol");
  if (goals.length === 0) return null;
  return [goals.filter((i) => i.team?.id === homeId).length, goals.filter((i) => i.team?.id === awayId).length];
}

const TICKS = [0, 15, 30, 45, 60, 75, 90];

function Lane({
  placed, side, color, editorial, h,
}: { placed: Placed[]; side: "home" | "away"; color: string; editorial: boolean; h: number }) {
  return (
    <div className={`tl__lane tl__lane--${side}`} style={{ height: h, width: AXIS_W, "--c": color } as CSSProperties}>
      <svg className="tl__stems" width={AXIS_W} height={h} aria-hidden="true">
        {placed.map((p) => {
          const y0 = side === "home" ? h : 0;
          const y1 = side === "home" ? h - STEM : STEM;
          // guías siempre verticales: salen de su minuto en el eje; el icono puede desplazarse a un lado pero la guía no se tuerce
          return <line key={p.item.id} x1={p.trueX} y1={y0} x2={p.trueX} y2={y1} stroke={color} strokeWidth={2.5} strokeOpacity={0.8} strokeLinecap="round" />;
        })}
      </svg>
      {placed.map((p, i) => {
        const status = p.item.status ?? "auto";
        const labelOff = p.icon + 2 + p.tier * LABEL_H;
        return (
          <motion.div
            key={p.item.id}
            className={`tl__ev tl__ev--${side}${p.item.major ? " tl__ev--major" : ""}${editorial ? ` tl__ev--${status}` : ""}`}
            style={{ left: p.x - p.w / 2, width: p.w, height: p.icon, [side === "home" ? "bottom" : "top"]: STEM } as CSSProperties}
            variants={popVariants}
            custom={i}
            data-testid="tl-event"
            data-type={eventKind(p.item.type)}
            data-status={editorial ? status : undefined}
            data-major={p.item.major ? "true" : "false"}
            title={p.item.label}
          >
            <EventIcon type={p.item.type} size={p.icon} color={color} status={status} editorial={editorial} />
            {p.text && (
              <span
                className="tl__t display"
                style={{ [side === "home" ? "bottom" : "top"]: labelOff, transform: `translateX(calc(-50% + ${p.shift}px))` } as CSSProperties}
              >
                <em>{p.item.minute}'</em> {p.text.slice(String(p.item.minute).length + 2)}
              </span>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

const laneHeight = (placed: Placed[]) => {
  const tiers = placed.reduce((m, p) => (p.text ? Math.max(m, p.tier + 1) : m), 1);
  return STEM + ICON_MAJOR + 2 + tiers * LABEL_H;
};

/**
 * Línea de tiempo del partido (tercio inferior): eje 0-90' con descanso, eventos del local arriba y del visitante abajo,
 * marcador y minuto en el hueco central. La vista de ANTENA (por defecto) pinta solo goles, tarjetas y cambios aprobados
 * o editados (`approved` / `edited`), sin ninguna marca de moderación; los eventos sin confirmar ("auto") y los descartados no
 * se pintan. Con `editorial` se ven todos los eventos con su estado.
 */
export function Timeline({ payload, demoData, editorial = false }: GraphicProps<"timeline">) {
  const { home, away, minute } = payload;
  const [ch, ca] = pairAccents(home.colors, away.colors);
  // antena: SOLO eventos confirmados (approved / edited) y solo goles, tarjetas y cambios; los "auto" y los descartados no
  // salen nunca. Con `editorial` se ve todo, con su estado.
  const items = editorial
    ? payload.items
    : payload.items.filter((i) => AIR_STATUS.includes(i.status ?? "auto") && AIR_KINDS.includes(eventKind(i.type)));
  const maxMin = Math.max(90, ...items.map((i) => i.minute ?? 0), minute ?? 0);
  const domain = maxMin <= 90 ? 90 : Math.ceil(maxMin) + 1;
  const pxPerMin = AXIS_W / domain;
  const homeP = layoutSide(items.filter((i) => i.team?.id === home.id), pxPerMin, AXIS_W, !editorial, !editorial);
  const awayP = layoutSide(items.filter((i) => i.team?.id === away.id), pxPerMin, AXIS_W, !editorial, !editorial);
  const now = minute != null ? Math.min(minute, domain) : null;
  const score = scoreOf(items, home.id, away.id);
  const hh = laneHeight(homeP);
  const ah = laneHeight(awayP);
  return (
    <Panel
      stripe={[home.colors.primary ?? ch, away.colors.primary ?? ca]}
      crest={false}
      demoData={demoData}
      demoBadge={false}
      format="lower"
      from="bottom"
      className="tl"
      style={{ "--ch": ch, "--ca": ca } as CSSProperties}
    >
      <div className="tl__row tl__row--top">
        <div className="tl__gutter tl__gutter--top">
          <TeamCrest team={home} size={36} />
          <b className="tl__team display caps">{home.short}</b>
        </div>
        <Lane placed={homeP} side="home" color={ch} editorial={editorial} h={hh} />
        {demoData && <span className="tl__badge"><DemoBadge /></span>}
      </div>

      <div className="tl__row">
        <div className="tl__gutter tl__gutter--mid" data-testid="tl-score">
          {score && (
            <b className="tl__score display num">{score[0]} <i className="tl__sep">–</i> {score[1]}</b>
          )}
          {now != null && <span className="tl__now display num">{now}'</span>}
        </div>
        <div className="tl__axis" style={{ width: AXIS_W }} data-testid="tl-axis">
          <div className="tl__rail" />
          {now != null && (
            <motion.div
              className="tl__done"
              style={{ width: now * pxPerMin, transformOrigin: "left center" }}
              variants={growVariants}
              data-testid="tl-progress"
            />
          )}
          <i className="tl__ht" style={{ left: 45 * pxPerMin }} data-testid="tl-halftime" />
          {TICKS.filter((t) => t <= domain).map((t) => (
            <span
              key={t}
              className={`tl__tick display num${t === 45 ? " tl__tick--ht" : ""}`}
              style={{ left: t * pxPerMin, transform: t === 0 ? "none" : t === 90 ? "translateX(-100%)" : "translateX(-50%)" }}
            >
              {t === 45 ? "DESCANSO" : `${t}'`}
            </span>
          ))}
          {homeP.map((p) => (
            <i key={p.item.id} className="tl__dot" style={{ left: p.trueX, background: ch }} />
          ))}
          {awayP.map((p) => (
            <i key={p.item.id} className="tl__dot" style={{ left: p.trueX, background: ca }} />
          ))}
          {now != null && <i className="tl__nowline" style={{ left: now * pxPerMin }} />}
        </div>
      </div>

      <div className="tl__row">
        <div className="tl__gutter tl__gutter--bottom">
          <TeamCrest team={away} size={36} />
          <b className="tl__team display caps">{away.short}</b>
        </div>
        <Lane placed={awayP} side="away" color={ca} editorial={editorial} h={ah} />
      </div>
      <span className="tl__sr">{items.map((i) => `${i.minute}' ${EVENT_NAME[eventKind(i.type)]}`).join(", ")}</span>
    </Panel>
  );
}
