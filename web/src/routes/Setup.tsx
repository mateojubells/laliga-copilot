import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { LineupProposal, MatchListItem, PlayerRef, SeasonInfoOut, SessionInfo, TeamLineup, TeamRef } from "../contracts";
import { TeamCrest } from "../design";
import { api } from "../live/api";
import { isTooQuiet } from "../live/audio/meter";
import { useLive } from "../live";
import { buildChecks, canStart } from "../setup/checks";
import { byLine, clickMove, movePlayer, slotOf, validateLineup, type Slot } from "../setup/lineup";
import { MicTest } from "../setup/MicTest";
import "./Setup.css";

type Voice = "mic" | "replay" | "none";

/** Sólo el partido de prueba tiene audio de repetición. */
export function replayAvailable(season: string | undefined, m: Pick<MatchListItem, "id" | "round"> | null): boolean {
  return season === "2024-25" && !!m && m.round === 4 && m.id.includes("barcelona") && m.id.includes("valladolid");
}

/** Hook de carga con reintento cada 3 s (el servidor puede estar arrancando). */
function useRetrying<T>(load: (() => Promise<T>) | null, deps: unknown[]): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    setData(null); setError(null);
    if (!load) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const go = () => load().then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e: Error) => { if (alive) { setError(e.message); timer = setTimeout(go, 3000); } });
    go();
    return () => { alive = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps]);
  return { data, error, loading: !!load && data == null && error == null, reload: () => setNonce((n) => n + 1) };
}

const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });
};

function Section({ n, title, children, hint }: { n: number; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="su-sec" aria-labelledby={`su-h${n}`}>
      <h2 id={`su-h${n}`}><span className="su-n">{n}</span>{title}</h2>
      {hint && <p className="su-hint">{hint}</p>}
      {children}
    </section>
  );
}

function ErrorLine({ msg }: { msg: string | null }) {
  return msg ? <p className="su-note bad" role="alert">{msg} Reintentando…</p> : null;
}

/** Menú principal: prepara el partido (temporada, partido, alineaciones, voz, opciones) y lo arranca. */
export function Setup() {
  const navigate = useNavigate();
  const { state: live } = useLive("operator", { snapshot: false });

  // --- partido en curso
  const current = useRetrying<SessionInfo>(() => api.session(), []);
  const [endAsk, setEndAsk] = useState(false);
  const [endBusy, setEndBusy] = useState(false);
  const [endErr, setEndErr] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const running = !dismissed && current.data?.config ? current.data : null;

  // --- 1 temporada
  const seasons = useRetrying<SeasonInfoOut[]>(() => api.seasons(), []);
  const [season, setSeason] = useState<string>("");
  useEffect(() => {
    if (!seasons.data?.length || season) return;
    setSeason((seasons.data.find((s) => s.current) ?? seasons.data[seasons.data.length - 1]).season);
  }, [seasons.data, season]);
  const seasonInfo = seasons.data?.find((s) => s.season === season) ?? null;

  // --- 2 partido
  const matches = useRetrying<MatchListItem[]>(season ? () => api.matches(season) : null, [season]);
  const [round, setRound] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [matchId, setMatchId] = useState<string>("");
  const rounds = useMemo(() => [...new Set((matches.data ?? []).map((m) => m.round))].sort((a, b) => a - b), [matches.data]);
  useEffect(() => {
    setMatchId(""); setRound(null);
  }, [season]);
  useEffect(() => {
    if (!matches.data?.length || round != null) return;
    const open = matches.data.find((m) => m.home_goals == null);
    setRound(open ? open.round : rounds[0]);
  }, [matches.data, rounds, round]);
  const q = query.trim().toLowerCase();
  const shown = useMemo(() => {
    const all = matches.data ?? [];
    const list = q ? all.filter((m) => `${m.home.name} ${m.away.name} ${m.home.short} ${m.away.short}`.toLowerCase().includes(q)) : all.filter((m) => m.round === round);
    return list;
  }, [matches.data, q, round]);
  const match = matches.data?.find((m) => m.id === matchId) ?? null;

  // --- 3 alineaciones
  const proposal = useRetrying<LineupProposal>(match ? () => api.lineup(match.id) : null, [match?.id]);
  const [lineups, setLineups] = useState<Record<string, TeamLineup>>({});
  useEffect(() => {
    if (proposal.data) setLineups(structuredClone(proposal.data.teams));
  }, [proposal.data]);
  const teamsOfMatch: TeamRef[] = match ? [match.home, match.away] : [];
  const lineupsLoaded = !!(match && proposal.data && teamsOfMatch.every((t) => lineups[t.id]));
  const lineupErrors = useMemo(() => {
    if (!lineupsLoaded || !proposal.data) return [];
    return teamsOfMatch.flatMap((t) => validateLineup(lineups[t.id], proposal.data!.squads[t.id] ?? []).errors.map((e) => `${t.short}: ${e}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lineups, proposal.data, lineupsLoaded, match?.id]);

  // --- 4 voz, 5 opciones
  const [voice, setVoice] = useState<Voice>("mic");
  const [auto, setAuto] = useState(false);
  const [micPeak, setMicPeak] = useState<number | null>(null);
  const onMic = useCallback((r: { peak: number } | null) => setMicPeak(r ? r.peak : null), []);
  const replayOk = replayAvailable(season, match);
  useEffect(() => { if (voice === "replay" && !replayOk) setVoice("mic"); }, [voice, replayOk]);

  // --- 6 comprobaciones y 7 empezar
  const checks = buildChecks({
    serverOk: seasons.data ? true : seasons.error ? false : null,
    serverError: seasons.error ?? undefined,
    seasonHasResults: seasonInfo ? seasonInfo.has_results : null,
    matchChosen: !!match,
    lineupErrors, lineupsLoaded,
    voice, micPeak, micTooQuiet: micPeak != null && isTooQuiet(micPeak),
    programClients: live.connected ? live.status.program_clients ?? null : null,
  });
  const ready = canStart(checks);
  const [starting, setStarting] = useState(false);
  const [startErr, setStartErr] = useState<string | null>(null);

  const start = async () => {
    if (!match) return;
    setStarting(true); setStartErr(null);
    try {
      await api.startSession({ season, match: match.id, lineups, voice, auto_program: auto });
      navigate("/");
    } catch (e) {
      setStartErr((e as Error).message);
      setStarting(false);
    }
  };
  const endCurrent = async () => {
    setEndBusy(true); setEndErr(null);
    try { await api.endSession(); setDismissed(true); setEndAsk(false); }
    catch (e) { setEndErr((e as Error).message); }
    finally { setEndBusy(false); }
  };

  const setTeamLineup = (teamId: string, f: (l: TeamLineup) => TeamLineup) => setLineups((all) => ({ ...all, [teamId]: f(all[teamId]) }));

  return (
    <div className="su" data-testid="setup">
      <header className="su-head">
        <h1>LaLiga Copilot <small>Preparar partido</small></h1>
        <span className={`su-chip ${live.connected ? "ok" : "bad"}`}><i /> {live.connected ? "Servidor conectado" : "Sin conexión con el servidor"}</span>
      </header>

      <main className="su-main">
        {running && (
          <div className="su-banner" role="status" data-testid="su-running">
            <div>
              <b>Hay un partido en curso</b>
              <span className="su-dim">
                {" "}{running.home?.name ?? running.config?.match} – {running.away?.name ?? ""}
                {running.score ? ` · ${Object.values(running.score).join("–")}` : ""}
                {running.resumed ? " · restaurado tras un reinicio" : ""}
              </span>
            </div>
            <div className="su-row">
              <button type="button" className="su-btn primary" onClick={() => navigate("/")} data-testid="su-continue">Continuar partido en curso</button>
              {!endAsk && <button type="button" className="su-btn" onClick={() => setEndAsk(true)} data-testid="su-end">Terminar y preparar otro</button>}
              {endAsk && (
                <span className="su-confirm" role="alertdialog" aria-label="Confirmar terminar partido">
                  ¿Terminar y archivar el partido en curso?
                  <button type="button" className="su-btn danger" disabled={endBusy} onClick={() => void endCurrent()} data-testid="su-end-confirm">Sí, terminar</button>
                  <button type="button" className="su-btn" disabled={endBusy} onClick={() => setEndAsk(false)}>No</button>
                </span>
              )}
            </div>
            {endErr && <p className="su-note bad" role="alert">{endErr}</p>}
          </div>
        )}

        <Section n={1} title="Temporada" hint="Se muestran las temporadas instaladas en el servidor.">
          <ErrorLine msg={seasons.error} />
          {seasons.loading && <p className="su-dim">Cargando temporadas…</p>}
          <div className="su-cards">
            {(seasons.data ?? []).map((s) => (
              <button key={s.season} type="button" aria-pressed={s.season === season} className={`su-card ${s.season === season ? "sel" : ""}`}
                onClick={() => setSeason(s.season)} data-testid={`su-season-${s.season}`}>
                <b className="display">{s.season}</b>
                <span className="su-dim">{s.teams} equipos · {s.players} jugadores</span>
                <span className="su-tags">
                  <span className={`su-tag ${s.has_results ? "ok" : ""}`}>{s.has_results ? "Resultados reales" : "Sin resultados"}</span>
                  {s.has_stats && <span className="su-tag demo">Estadísticas de demostración</span>}
                  {s.current && <span className="su-tag">En curso</span>}
                </span>
              </button>
            ))}
          </div>
        </Section>

        <Section n={2} title="Partido" hint="Elige jornada y partido, o busca por equipo.">
          {!season && <p className="su-dim">Elige primero una temporada.</p>}
          {season && (
            <>
              <ErrorLine msg={matches.error} />
              <div className="su-row su-wrap">
                <label className="su-field">Jornada
                  <select value={round ?? ""} onChange={(e) => { setRound(Number(e.target.value)); setQuery(""); }} disabled={!rounds.length} data-testid="su-round">
                    {rounds.map((r) => <option key={r} value={r}>Jornada {r}</option>)}
                  </select>
                </label>
                <label className="su-field grow">Buscar equipo
                  <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Barcelona, Valladolid…" data-testid="su-search" />
                </label>
              </div>
              {matches.loading && <p className="su-dim">Cargando partidos…</p>}
              {!matches.loading && !matches.error && !shown.length && <p className="su-dim">No hay partidos que coincidan.</p>}
              <ul className="su-matches">
                {shown.map((m) => (
                  <li key={m.id}>
                    <button type="button" aria-pressed={m.id === matchId} className={`su-match ${m.id === matchId ? "sel" : ""}`} onClick={() => setMatchId(m.id)} data-testid={`su-match-${m.id}`}>
                      <span className="su-team home">{m.home.name}<TeamCrest team={m.home} size={26} /></span>
                      <span className="su-score num">{m.home_goals != null && m.away_goals != null ? `${m.home_goals} – ${m.away_goals}` : "vs"}</span>
                      <span className="su-team away"><TeamCrest team={m.away} size={26} />{m.away.name}</span>
                      <span className="su-meta">
                        {q ? `J${m.round} · ` : ""}{fmtDate(m.date)}
                        {m.has_lineup && <span className="su-tag ok">Alineación guardada</span>}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>

        <Section n={3} title="Alineaciones" hint="Clic en un jugador: titular ↔ banquillo. Con × lo quitas de la convocatoria; clic en «No convocado» lo manda al banquillo. Hacen falta 11 titulares con 1 portero.">
          {!match && <p className="su-dim">Elige un partido para ver las alineaciones.</p>}
          {match && <ErrorLine msg={proposal.error} />}
          {match && proposal.loading && <p className="su-dim">Cargando alineaciones…</p>}
          {match && lineupsLoaded && proposal.data && (
            <>
              <p className="su-dim">
                {proposal.data.source === "saved" ? "Alineación guardada de este partido." : "Propuesta automática: los jugadores con más partidos por posición."}{" "}
                <button type="button" className="su-link" onClick={() => setLineups(structuredClone(proposal.data!.teams))} data-testid="su-reset">Restablecer propuesta</button>
              </p>
              <div className="su-lineups">
                {teamsOfMatch.map((t) => (
                  <TeamColumn key={t.id} team={t} squad={proposal.data!.squads[t.id] ?? []} lu={lineups[t.id]}
                    onClick={(id) => setTeamLineup(t.id, (l) => clickMove(l, id))}
                    onMove={(id, to) => setTeamLineup(t.id, (l) => movePlayer(l, id, to))} />
                ))}
              </div>
            </>
          )}
        </Section>

        <Section n={4} title="Voz" hint="De dónde viene lo que dice el comentarista.">
          <div className="su-radios" role="radiogroup" aria-label="Fuente de voz">
            <Radio checked={voice === "mic"} onChange={() => setVoice("mic")} label="Micrófono de este Mac" id="mic" />
            <Radio checked={voice === "replay"} onChange={() => setVoice("replay")} label="Repetición del partido de prueba" id="replay" disabled={!replayOk}
              note={replayOk ? undefined : "Sólo con 2024-25 · J04 · Barcelona–Valladolid"} />
            <Radio checked={voice === "none"} onChange={() => setVoice("none")} label="Sin voz (sólo operador)" id="none" />
          </div>
          {voice === "mic" && <MicTest onResult={onMic} />}
        </Section>

        <Section n={5} title="Opciones">
          <label className="su-check">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} data-testid="su-auto" />
            <span><b>Modo automático</b> <span className="su-dim">— las propuestas de prioridad alta salen solas a programa. Puedes cambiarlo en directo.</span></span>
          </label>
        </Section>

        <Section n={6} title="Comprobación previa">
          <ul className="su-checks" data-testid="su-checks">
            {checks.map((c) => (
              <li key={c.id} className={`su-ck ${c.status}`}>
                <i aria-hidden>{c.status === "ok" ? "✓" : c.status === "bad" ? "✕" : c.status === "warn" ? "!" : "…"}</i>
                <span><b>{c.label}</b> <span className="su-dim">{c.detail}</span></span>
              </li>
            ))}
          </ul>
          <button type="button" className="su-btn" onClick={() => window.open("/program", "laliga-program", "popup,width=1280,height=720")}>Abrir salida de programa</button>
        </Section>

        <Section n={7} title="Empezar">
          {startErr && <p className="su-note bad" role="alert" data-testid="su-start-error">{startErr}</p>}
          <button type="button" className="su-go" disabled={!ready || starting} onClick={() => void start()} data-testid="su-start">
            {starting ? "Empezando…" : "Empezar partido"}
          </button>
          {!ready && <p className="su-dim">Completa las comprobaciones en rojo o pendientes para poder empezar.</p>}
        </Section>
      </main>
    </div>
  );
}

function Radio({ checked, onChange, label, id, disabled, note }: { checked: boolean; onChange: () => void; label: string; id: string; disabled?: boolean; note?: string }) {
  return (
    <label className={`su-radio ${checked ? "sel" : ""} ${disabled ? "off" : ""}`}>
      <input type="radio" name="voice" value={id} checked={checked} disabled={disabled} onChange={onChange} data-testid={`su-voice-${id}`} />
      <span>{label}{note && <small className="su-dim"> · {note}</small>}</span>
    </label>
  );
}

function TeamColumn({ team, squad, lu, onClick, onMove }: {
  team: TeamRef; squad: PlayerRef[]; lu: TeamLineup; onClick: (id: string) => void; onMove: (id: string, to: Slot) => void;
}) {
  const v = validateLineup(lu, squad);
  const byId = new Map(squad.map((p) => [p.id, p]));
  const pick = (ids: string[]) => ids.map((id) => byId.get(id)).filter((p): p is PlayerRef => !!p).sort(byLine);
  const out = squad.filter((p) => slotOf(lu, p.id) === "out").sort(byLine);
  const group = (title: string, players: PlayerRef[], slot: Slot, extra?: string) => (
    <div className="su-group" data-testid={`su-${team.id}-${slot}`}>
      <h4>{title} <span className="su-dim">{players.length}{extra}</span></h4>
      <ul>
        {players.map((p) => (
          <li key={p.id}>
            <button type="button" className="su-pl" onClick={() => onClick(p.id)} title={slot === "starting" ? "Pasar al banquillo" : "Pasar a titular"} data-testid={`su-pl-${p.id}`}>
              <span className="su-num num">{p.number ?? "–"}</span>
              <span className="su-pos">{p.position}</span>
              <span className="su-pname">{p.known_as}</span>
            </button>
            {slot !== "out" && <button type="button" className="su-x" aria-label={`Quitar a ${p.known_as} de la convocatoria`} onClick={() => onMove(p.id, "out")}>×</button>}
          </li>
        ))}
        {!players.length && <li className="su-dim">—</li>}
      </ul>
    </div>
  );
  return (
    <div className="su-col">
      <h3><TeamCrest team={team} size={24} /> {team.name}</h3>
      <p className={`su-valid ${v.ok ? "ok" : "bad"}`} role="status" data-testid={`su-valid-${team.id}`}>
        {v.ok ? "✓ 11 titulares y portero" : v.errors.join(" ")} <span className="su-dim">({v.starters} titulares · {v.keepers} portero{v.keepers === 1 ? "" : "s"})</span>
      </p>
      {group("Titulares", pick(lu.starting), "starting")}
      {group("Banquillo", pick(lu.bench), "bench")}
      {group("No convocado", out, "out")}
    </div>
  );
}
