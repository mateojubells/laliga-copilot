import { StatTile, accentOn } from "../design";
import type { Shot } from "../contracts";
import { AttackArrow, Pitch, ShotGlyph, fitView, ShotsLayer, SHOT_OUTCOME_LABEL, SHOT_R_MAX, SHOT_R_MIN, shotRadiusM } from "../pitch";
import "./ShotMap.css";
import { FIELD_PAD, FIELD_TOP_BAND, FieldShell, Reveal, nameOfSubject, teamOfSubject } from "./shared";
import type { GraphicProps } from "./types";

const PITCH_W = 400;
/** Encuadre a la zona de tiro (nunca medio campo): ninguna marca de dato por debajo de 9 px/m (el medio campo daba 7,2). */
const MIN_K = 9;
const OUTCOMES: Shot["outcome"][] = ["goal", "saved", "post", "blocked", "off"];
const XG_SAMPLES = [0.05, 0.3, 0.75];
const es2 = (n: number) => n.toFixed(2).replace(".", ",");
const es1 = (n: number) => n.toFixed(1).replace(".", ",");

/** "8 goles con 5,2 de xG: 2,8 por encima de lo esperado" (null sin tiros: no hay historia). */
export function shotHeadline(goals: number, xg: number, shots: number): string | null {
  if (shots === 0 || !Number.isFinite(goals) || !Number.isFinite(xg)) return null;
  const d = goals - xg;
  const verdict = Math.abs(d) < 0.5 ? "en línea con lo esperado" : d > 0 ? `${es1(d)} por encima de lo esperado` : `${es1(-d)} por debajo de lo esperado`;
  return `${goals} ${goals === 1 ? "gol" : "goles"} con ${es1(xg)} de xG: ${verdict}`;
}
/** Las tres cifras que cuentan en 10 segundos. */
const TOTAL_KEYS = ["shots", "goals", "xg"];

/** Mapa de tiros: medio campo atacante (portería a la derecha), círculos con área ∝ xG y estilo por resultado. */
export function ShotMap({ payload, demoData }: GraphicProps<"shot_map">) {
  const { subject, subject_type: type, shots, totals, scope } = payload;
  const team = teamOfSubject(subject, type);
  const accent = accentOn(team.colors.primary ?? "#7cc4ff");
  const count = (o: Shot["outcome"]) => shots.filter((s) => s.outcome === o).length;
  // zona de tiro: caja de los tiros (y la portería) + 4 m, recortada para no bajar de MIN_K px/m
  const view = fitView(shots.length ? [...shots.map((s) => [s.x, s.y] as [number, number]), [105, 34]] : [], {
    width: PITCH_W, padding: FIELD_PAD, margin: 4, minK: MIN_K, minPlotH: 420, maxPlotH: 500, anchor: "right",
    fallback: { x0: 66, x1: 105, y0: 8, y1: 60 },
  });
  const k = (PITCH_W - FIELD_PAD) / (105 - view.x0);
  const num = (key: string) => totals.find((t) => t.key === key)?.value;
  const headline = shotHeadline(num("goals") ?? count("goal"), num("xg") ?? shots.reduce((s, x) => s + x.xg, 0), shots.length);
  const picked = TOTAL_KEYS.flatMap((key) => totals.filter((t) => t.key === key));
  const tiles = (picked.length === 3 ? picked : totals.slice(0, 3));
  return (
    <FieldShell
      kicker="Mapa de tiros"
      title={nameOfSubject(subject, type)}
      team={team}
      scope={scope.label}
      demoData={demoData}
      pitchW={PITCH_W}
      pitchSide="right"
      className="sm"
      pitch={
        <Pitch view={view} width={PITCH_W} padding={FIELD_PAD} topBand={FIELD_TOP_BAND} accent={accent} label={`Mapa de tiros de ${nameOfSubject(subject, type)}`}>
          <ShotsLayer shots={shots} legend={false} />
          <AttackArrow />
        </Pitch>
      }
      side={
        <>
          <Reveal className="sm__totals sd__tiles">
            {tiles.map((t) => (
              <StatTile key={t.key} label={t.label} value={t.display} highlight={t.highlight} />
            ))}
          </Reveal>
          {headline && (
            <Reveal className="sd__headline sm__headline" data-testid="sm-headline">
              {headline}
            </Reveal>
          )}
          <Reveal className="sm__legends">
            <div className="lg sm__outcomes" data-testid="sm-outcomes">
              {OUTCOMES.map((o) => (
                <div className="lg__row" key={o} data-outcome={o}>
                  <ShotGlyph outcome={o} r={13} accent={accent} />
                  {SHOT_OUTCOME_LABEL[o]}
                  <b className="num">{count(o)}</b>
                </div>
              ))}
            </div>
            <div className="sm__leg">
              <div className="sd__label">Tamaño = xG</div>
              {/* tres celdas fijas de 96 px: el círculo centrado y el valor debajo (los valores nunca se tocan) */}
              <svg className="sm__xg" width={288} height={76} viewBox="0 0 288 76" data-testid="sm-xg-legend" role="img" aria-label="Escala de xG">
                {XG_SAMPLES.map((v, i) => {
                  const cx = 48 + i * 96;
                  return (
                    <g key={v}>
                      <circle cx={cx} cy={24} r={Math.min(SHOT_R_MAX, Math.max(SHOT_R_MIN, shotRadiusM(v) * k))} fill="rgba(255,255,255,0.12)" stroke="rgba(255,255,255,0.85)" strokeWidth={2.5} />
                      <text x={cx} y={70} textAnchor="middle" fontFamily="var(--font-text)" fontSize={24} fontWeight={600} fill="#cbd3df">{es2(v)}</text>
                    </g>
                  );
                })}
              </svg>
            </div>
          </Reveal>
        </>
      }
    />
  );
}
