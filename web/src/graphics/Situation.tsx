import type { PlayerRef, Stat, TeamRef } from "../contracts";
import { DemoBadge, NumberPill, Panel, TeamCrest, accentOn, inkOn } from "../design";
import { Pitch, ShotsLayer } from "../pitch";
import "./Situation.css";
import { Reveal, nameOfSubject, teamOfSubject } from "./shared";
import type { GraphicProps } from "./types";

const PITCH_W = 280;

/** Foto o nada: un jugador sin foto va con su dorsal en píldora del club (nunca una silueta); un equipo, con su escudo. */
function Face({ s, type }: { s: PlayerRef | TeamRef; type: "player" | "team" }) {
  if (type === "team") return <TeamCrest team={s as TeamRef} size={52} />;
  const p = s as PlayerRef;
  return p.number != null ? <NumberPill number={p.number} className="si__pill" /> : null;
}

/** "2 · 2" → "2 DE 2" (con un punto medio no se sabe qué es cada número). Cualquier otro valor se deja tal cual. */
export function Ratio({ display }: { display: string }) {
  const m = display.match(/^(\d+)\s*[·•/]\s*(\d+)$/);
  if (!m) return <>{display}</>;
  return (
    <>
      {m[1]}
      <small>de</small>
      {m[2]}
    </>
  );
}

/** Las dos cifras de la derecha: la destacada y, después, la de acierto ("2 · 2") si la hay, que cuenta más que un total de temporada. */
export function pickFigs(stats: readonly Stat[]): Stat[] {
  const ratio = (s: Stat) => /^\d+\s*[·•/]\s*\d+$/.test(s.display);
  const first = stats.find((s) => s.highlight) ?? stats[0];
  if (!first) return [];
  const rest = stats.filter((s) => s !== first);
  const second = rest.find(ratio) ?? rest[0];
  return second ? [first, second] : [first];
}

/** "Faltas recibidas hoy" → "faltas recibidas": el "hoy" ya lo dice la etiqueta de la banda. */
const todayLabel = (s: Stat) => {
  const t = s.label.replace(/\s+(hoy|en este partido)$/i, "");
  return t.charAt(0).toLowerCase() + t.slice(1);
};

/** Título en una línea: "PENALTI" en bloque del color del club y "PROVOCADO" en blanco, sin píldora que repita lo mismo. */
export function titleParts(title: string, role?: string | null): { lead: string; rest: string } {
  if (!role) return { lead: title, rest: "" };
  if (role.toLowerCase().startsWith(title.toLowerCase())) return { lead: role.slice(0, title.length), rest: role.slice(title.length).trim() };
  return { lead: title, rest: role };
}

/**
 * Situación de juego (tercio inferior): tipo en grande, protagonista (+ otro jugador), dos cifras del histórico y la banda
 * de "hoy". Deja ver la jugada. Solo las situaciones con tiros que no son penalti (falta, tiro) llevan campo completo.
 */
export function Situation({ payload, demoData }: GraphicProps<"situation">) {
  const { event_type, title, subject, subject_type: type, other, role_label, scope, stats, this_match, shots } = payload;
  const t = type ?? "player";
  const team = subject ? teamOfSubject(subject, t) : (other?.team ?? undefined);
  const hasField = event_type !== "penalti" && !!shots && shots.length > 0;
  const accent = accentOn(team?.colors.primary ?? "#7cc4ff");
  const { lead, rest } = titleParts(title, role_label);
  const figs = pickFigs(stats);
  return (
    <Panel
      team={team}
      demoData={demoData}
      demoBadge={false}
      crest={false}
      format="lower"
      from="bottom"
      className="si"
    >
      <div className="si__grid" style={{ gridTemplateColumns: `minmax(0, 1fr) auto${hasField ? ` ${PITCH_W}px` : ""}` }}>
        <Reveal className="si__main">
          <h2 className={`si__title display caps${(lead + rest).length > 16 ? " si__title--long" : ""}`} data-testid="si-title">
            <span className="si__lead">{lead}</span>
            {rest && <span className="si__rest"> {rest}</span>}
          </h2>
          {subject && (
            <div className="si__who">
              <Face s={subject} type={t} />
              <div className="si__name display caps" data-testid="si-subject">{nameOfSubject(subject, t)}</div>
              {other && (
                <div className="si__other" data-testid="si-other">
                  <span>frente a</span>
                  {other.number != null && (
                    <NumberPill number={other.number} fill={other.team.colors.primary ?? undefined} ink={other.team.colors.text ?? inkOn(other.team.colors.primary ?? "#445")} className="si__pill" />
                  )}
                  <b className="si__other-n display caps">{other.known_as}</b>
                </div>
              )}
            </div>
          )}
          {/* ámbito, distintivo de demostración y escudo en una línea al pie del bloque: sin franja de cabecera vacía */}
          <div className="si__meta">
            {team && <TeamCrest team={team} size={32} />}
            <span>{scope.label}</span>
            {demoData && <DemoBadge />}
          </div>
        </Reveal>

        <div className="si__side">
          {figs.length > 0 && (
            <div className="si__figs">
              {figs.map((s) => (
                <Reveal key={s.key} className={`si__fig${s.highlight ? " is-hl" : ""}`}>
                  <span className="si__fig-l">{s.label}</span>
                  <b className="si__fig-v display num" data-testid="si-fig"><Ratio display={s.display} /></b>
                </Reveal>
              ))}
            </div>
          )}
          {this_match && this_match.length > 0 && (
            <Reveal className="si__match">
              <span className="si__match-l caps">Hoy</span>
              <div className="si__match-v" data-testid="si-match">
                {this_match.map((s) => (
                  <span key={s.key} className="si__m">
                    <b className="si__m-v display num">{s.display}</b>
                    <i>{todayLabel(s)}</i>
                  </span>
                ))}
              </div>
            </Reveal>
          )}
        </div>

        {hasField && (
          <Reveal className="si__field">
            <Pitch width={PITCH_W} padding={8} accent={accent} label="Posición de la situación">
              <ShotsLayer shots={shots!} legend={false} dotRadius={12} />
            </Pitch>
          </Reveal>
        )}
      </div>
    </Panel>
  );
}
