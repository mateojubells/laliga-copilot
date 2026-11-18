"""Contrato de los grafismos: qué datos recibe el frontend para pintar cada tipo (docs/ARCHITECTURE.md §5).

Cada payload es autosuficiente: el frontend NO consulta nada más para pintarlo. Se exporta a JSON Schema
(`python -m copilot.graphics.payloads`) y de ahí a TypeScript (web/src/contracts/), de modo que backend y frontend
se desarrollan en paralelo contra el mismo contrato.

Coordenadas: campo 105×68 m, origen abajo-izquierda, el equipo del grafismo ataca hacia x creciente.
"""
from __future__ import annotations

import json
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter

from copilot.types import Line, Position


# ------------------------------------------------------------------ piezas comunes
class TeamRef(BaseModel):
    id: str
    name: str
    short: str
    colors: dict[str, str]  # primary, secondary, text
    crest: str  # URL de /api/img/crest/<id>.svg (ImageProvider)


class PlayerRef(BaseModel):
    id: str
    name: str
    known_as: str
    number: Optional[int] = None
    position: Position
    line: Line
    team: TeamRef
    avatar: str  # URL de /api/img/player/<id>.svg


class Stat(BaseModel):
    key: str  # goals, assists, xg, key_passes, dribbles_won, ...
    label: str  # texto ya en español, listo para pintar: "Goles", "Pases clave"
    value: float
    display: str  # valor formateado: "4", "0,62", "87 %"
    per90: Optional[float] = None
    percentile: Optional[int] = None  # 0-100 frente a su grupo de comparación
    highlight: bool = False  # el dato que motivó el grafismo


class PercentileContext(BaseModel):
    group: str  # "Extremos de LaLiga"
    n: int  # jugadores en el grupo
    min_minutes: int


class Scope(BaseModel):
    """A qué periodo corresponden los datos (siempre anterior al partido en curso, salvo kind=match)."""
    kind: Literal["season", "match", "last_n"]
    label: str  # "LaLiga 2024-25 · hasta la J3"
    season: str
    until_round: Optional[int] = None
    match: Optional[str] = None


class Shot(BaseModel):
    x: float
    y: float
    xg: float
    outcome: Literal["goal", "saved", "off", "blocked", "post"]
    minute: int
    player: str  # id
    player_name: str
    body: Optional[str] = None


class Arrow(BaseModel):
    x: float
    y: float
    end_x: float
    end_y: float
    kind: Literal["pass", "key_pass", "assist", "cross", "carry"] = "pass"


# ------------------------------------------------------------------ payloads por tipo
class PlayerCard(BaseModel):
    kind: Literal["player_card"] = "player_card"
    player: PlayerRef
    scope: Scope
    headline: Optional[str] = None  # "4 goles en 3 partidos"
    stats: list[Stat]  # 4-6, ordenadas por relevancia para su posición y para el disparador
    percentile_context: Optional[PercentileContext] = None
    form: list[Stat] = Field(default_factory=list)  # últimos partidos (opcional)
    match_line: Optional[str] = None  # lo que lleva en el partido en curso según la timeline: "1 gol · 2 tiros"


class TeamCard(BaseModel):
    kind: Literal["team_card"] = "team_card"
    team: TeamRef
    scope: Scope
    position: Optional[int] = None
    points: Optional[int] = None
    form: list[Literal["W", "D", "L"]] = Field(default_factory=list)
    stats: list[Stat]


class NetNode(BaseModel):
    player: PlayerRef
    x: float
    y: float
    passes: int
    touches: int
    highlight: bool = False


class NetEdge(BaseModel):
    a: str  # id de jugador
    b: str
    count: int  # a → b
    highlight: bool = False


class PassNetworkG(BaseModel):
    kind: Literal["pass_network"] = "pass_network"
    team: TeamRef
    scope: Scope
    nodes: list[NetNode]  # 11
    edges: list[NetEdge]  # ya filtradas (mínimo de pases) y dirigidas
    min_passes: int
    headline: Optional[str] = None  # "Pedri, eje del juego: 71 pases por partido"


class ConnectionG(BaseModel):
    kind: Literal["connection"] = "connection"
    a: PlayerRef
    b: PlayerRef
    scope: Scope
    a_to_b: int
    b_to_a: int
    key_passes: int
    assists: int
    rank_for_a: int  # b es el N.º destinatario de a
    headline: str  # "Pedri → Lamine: su socio n.º 1"
    arrows: list[Arrow]  # muestra representativa (≤40) para dibujar en el campo
    a_pos: tuple[float, float]  # posición media
    b_pos: tuple[float, float]


class ShotMap(BaseModel):
    kind: Literal["shot_map"] = "shot_map"
    subject: Union[PlayerRef, TeamRef]
    subject_type: Literal["player", "team"]
    scope: Scope
    shots: list[Shot]
    totals: list[Stat]  # tiros, a puerta, goles, xG, xG/tiro


class HeatMap(BaseModel):
    kind: Literal["heat_map"] = "heat_map"
    subject: Union[PlayerRef, TeamRef]
    subject_type: Literal["player", "team"]
    scope: Scope
    metric: Literal["touches", "recoveries", "passes_received", "shots"] = "touches"
    cols: int  # rejilla agregada: no se mandan miles de eventos
    rows: int
    grid: list[float]  # cols×rows valores normalizados 0-1, por filas desde y=0
    total: int
    zones: list[Stat] = Field(default_factory=list)  # "% por tercio", "% banda derecha"...
    headline: Optional[str] = None


class ComparisonRow(BaseModel):
    key: str
    label: str
    a: Stat
    b: Stat
    better: Literal["a", "b", "tie"]
    higher_is_better: bool = True


class Comparison(BaseModel):
    kind: Literal["comparison"] = "comparison"
    subject_type: Literal["player", "team"]
    a: Union[PlayerRef, TeamRef]
    b: Union[PlayerRef, TeamRef]
    scope: Scope
    rows: list[ComparisonRow]  # 5-7
    headline: Optional[str] = None


class StandingsRowG(BaseModel):
    pos: int
    team: TeamRef
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    gd: int
    points: int
    form: list[Literal["W", "D", "L"]] = Field(default_factory=list)
    zone: Optional[Literal["champions", "europa", "conference", "relegation"]] = None
    highlight: bool = False


class Standings(BaseModel):
    kind: Literal["standings"] = "standings"
    scope: Scope
    rows: list[StandingsRowG]  # tabla completa o ventana alrededor de los equipos del partido
    window: Literal["full", "top", "around"] = "full"
    live: bool = False  # incluye el marcador en curso


class H2HMatch(BaseModel):
    season: str
    date: str
    home: TeamRef
    away: TeamRef
    home_goals: int
    away_goals: int


class H2HG(BaseModel):
    kind: Literal["h2h"] = "h2h"
    a: TeamRef
    b: TeamRef
    played: int
    a_wins: int
    draws: int
    b_wins: int
    a_goals: int
    b_goals: int
    last: list[H2HMatch]


class Situation(BaseModel):
    """Situación de juego (penalti, falta, regate, córner…) con el histórico del protagonista."""
    kind: Literal["situation"] = "situation"
    event_type: str  # EventType
    title: str  # "Penalti"
    subject: Optional[Union[PlayerRef, TeamRef]] = None
    subject_type: Optional[Literal["player", "team"]] = None
    other: Optional[PlayerRef] = None  # víctima / receptor
    role_label: Optional[str] = None  # "Penalti provocado"
    scope: Scope
    stats: list[Stat]  # histórico relevante: "Penaltis provocados: 3", "Lanzados: 5 · Marcados: 4"
    this_match: list[Stat] = Field(default_factory=list)  # recuento de lo narrado en este partido
    shots: list[Shot] = Field(default_factory=list)  # p. ej. penaltis lanzados (para mini-campo)


class TimelineItem(BaseModel):
    id: str
    minute: Optional[int] = None
    period: Optional[int] = None
    t_audio: float
    type: str  # EventType
    label: str  # "Gol · Raphinha"
    team: Optional[TeamRef] = None
    players: list[PlayerRef] = Field(default_factory=list)
    status: Literal["auto", "approved", "edited", "discarded"] = "auto"
    major: bool = False  # gol, roja, penalti, cambio


class Timeline(BaseModel):
    kind: Literal["timeline"] = "timeline"
    home: TeamRef
    away: TeamRef
    items: list[TimelineItem]
    minute: Optional[int] = None


class Scorebug(BaseModel):
    kind: Literal["scorebug"] = "scorebug"
    home: TeamRef
    away: TeamRef
    home_goals: int
    away_goals: int
    minute: Optional[int] = None
    period: Optional[int] = None
    added: Optional[int] = None


Payload = Annotated[
    Union[PlayerCard, TeamCard, PassNetworkG, ConnectionG, ShotMap, HeatMap, Comparison, Standings, H2HG,
          Situation, Timeline, Scorebug],
    Field(discriminator="kind"),
]
PAYLOADS: dict[str, type[BaseModel]] = {m.model_fields["kind"].default: m for m in (
    PlayerCard, TeamCard, PassNetworkG, ConnectionG, ShotMap, HeatMap, Comparison, Standings, H2HG, Situation,
    Timeline, Scorebug)}


# ------------------------------------------------------------------ mensajes del WebSocket
class Graphic(BaseModel):
    """GraphicCommand tal como llega al navegador (payload tipado)."""
    id: str
    kind: str
    priority: int = 50
    ttl_ms: int = 12000
    pinned: bool = False
    state: Literal["proposed", "on_air", "retracted"] = "proposed"
    reason: dict = Field(default_factory=dict)  # trigger, text, trace_id
    payload: Payload
    demo_data: bool = True  # → distintivo "Datos de demostración"
    ts: dict[str, float] = Field(default_factory=dict)


class MatchState(BaseModel):
    match: str
    home: TeamRef
    away: TeamRef
    home_goals: int = 0
    away_goals: int = 0
    period: Literal[0, 1, 2, 3] = 0  # 0 previa, 1 primera, 2 segunda, 3 final
    minute: Optional[int] = None
    on_pitch: dict[str, list[str]] = Field(default_factory=dict)  # equipo -> ids en el campo
    possession_subject: Optional[str] = None  # último sujeto (para depurar correferencia)
    # reloj del partido: con clock_running, el minuto en cada instante es
    #   clock_base_s + (ahora_servidor_ms - clock_at_ms)/1000  (en segundos de partido dentro del periodo)
    clock_running: bool = False
    clock_base_s: float = 0.0  # segundos de partido (45:00 = 2700) en el instante clock_at_ms
    clock_at_ms: Optional[float] = None  # reloj del servidor (ms) en que se fijó clock_base_s
    added: Optional[int] = None  # minutos de descuento anunciados en el periodo en curso


class ServerMsg(BaseModel):
    """Servidor → navegador. type decide qué campo viene relleno."""
    type: Literal["hello", "transcript", "graphic", "graphic_hide", "program", "program_clear", "event",
                  "state", "status", "latency"]
    server_now: float  # reloj del servidor (ms) para sincronizar relojes
    graphic: Optional[Graphic] = None
    graphic_id: Optional[str] = None
    transcript: Optional[dict] = None  # Transcript
    event: Optional[dict] = None  # MatchEvent
    state: Optional[MatchState] = None
    data: Optional[dict] = None  # status / latency


class OperatorAction(BaseModel):
    """Navegador → servidor."""
    type: Literal["approve", "pin", "unpin", "discard", "take", "clear_program", "edit_event", "discard_event",
                  "add_event", "request", "set_auto", "replay_control", "say", "painted", "ping",
                  "clock", "voice", "panic", "set_score"]
    # clock: value = kickoff | half_time | second_half | full_time | set_minute (event={"minute": N, "second": S})
    #        | set_added (event={"minutes": N})
    # voice: value = start | stop (el audio del micro llega por el WebSocket binario /ws/audio)
    # panic: vacía programa y apaga el modo automático
    # set_score: event={"home": N, "away": N}
    graphic_id: Optional[str] = None
    event_id: Optional[str] = None
    event: Optional[dict] = None  # campos a cambiar (edit_event) o evento completo (add_event)
    request: Optional[dict] = None  # {"kind":"player_card","subject":"barcelona/pedri"}: grafismo a la carta
    text: Optional[str] = None  # "say": simular voz
    value: Optional[Union[bool, float, str]] = None
    t_paint: Optional[float] = None  # "painted": reloj del servidor estimado por el cliente (ms)
    client_now: Optional[float] = None  # "ping": para estimar el desfase de relojes


# ------------------------------------------------------------------ menú principal (REST)
class SeasonInfoOut(BaseModel):
    season: str
    teams: int
    players: int
    has_results: bool  # resultados reales descargados
    has_stats: bool  # estadísticas de demostración generadas
    current: bool = False


class MatchListItem(BaseModel):
    id: str
    season: str
    round: int
    date: str
    home: TeamRef
    away: TeamRef
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    has_lineup: bool = False  # hay una alineación guardada para este partido


class TeamLineup(BaseModel):
    starting: list[str]  # 11 ids, el primero suele ser el portero
    bench: list[str]


class LineupProposal(BaseModel):
    match: str
    source: Literal["saved", "proposed"]  # guardada de este partido, o propuesta automática
    teams: dict[str, TeamLineup]  # equipo -> alineación
    squads: dict[str, list[PlayerRef]]  # equipo -> plantilla completa, para editar


class SessionConfig(BaseModel):
    season: str
    match: str
    lineups: dict[str, TeamLineup]
    voice: Literal["mic", "replay", "none"] = "mic"
    auto_program: bool = False


class SessionInfo(BaseModel):
    config: Optional[SessionConfig] = None
    started_at: Optional[str] = None  # ISO
    resumed: bool = False  # se restauró de disco tras un reinicio
    home: Optional[TeamRef] = None
    away: Optional[TeamRef] = None
    events: int = 0
    score: Optional[dict[str, int]] = None


def json_schema() -> dict:
    defs: dict = {}
    out = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "CopilotContracts", "$defs": defs}
    for model in (ServerMsg, OperatorAction, SeasonInfoOut, MatchListItem, LineupProposal, SessionConfig, SessionInfo):
        s = TypeAdapter(model).json_schema(ref_template="#/$defs/{model}")
        defs.update(s.pop("$defs", {}))
        defs[model.__name__] = s
    return out


if __name__ == "__main__":
    print(json.dumps(json_schema(), ensure_ascii=False, indent=1))
