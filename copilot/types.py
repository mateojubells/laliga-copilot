"""Contrato de datos de LaLiga Copilot: todo lo que viaja por el bus o entre capas.

Fuente de verdad ejecutable de docs/ARCHITECTURE.md §5. No cambiar sin actualizar ese documento.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ------------------------------------------------------------------ taxonomía
EventType = Literal[
    "gol", "tiro", "parada", "palo", "ocasion", "pase", "centro", "asistencia", "regate",
    "falta", "penalti", "mano", "corner", "saque_banda", "saque_puerta", "fuera_juego",
    "amarilla", "roja", "cambio", "lesion", "robo", "perdida", "despeje", "var",
    "inicio", "descanso", "final",
]
EVENT_TYPES: tuple[str, ...] = EventType.__args__  # type: ignore[attr-defined]

Modality = Literal["real", "negated", "hypothetical", "query", "past"]
Role = Literal["actor", "receiver", "victim", "out", "team_for", "team_against"]
#: orden en que se busca el "objetivo" de un evento para la métrica (evento, actor, objetivo)
TARGET_ROLES: tuple[str, ...] = ("receiver", "victim", "out")
EntityVia = Literal["exact", "alias", "asr_alias", "phonetic", "fuzzy", "epithet", "coref", "number"]

Position = Literal["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
Line = Literal["GK", "DEF", "MID", "FWD"]

GraphicKind = Literal[
    "player_card", "pass_network", "connection", "shot_map", "heat_map", "comparison",
    "standings", "h2h", "team_card", "situation", "timeline", "scorebug",
]

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0


# ------------------------------------------------------------------ voz
class Word(BaseModel):
    w: str
    t0: float
    t1: float
    p: float = 1.0


class Transcript(BaseModel):
    trace_id: str
    engine: str
    final: bool
    text: str
    t0: float  # segundos de audio desde el inicio de la fuente
    t1: float
    words: list[Word] = Field(default_factory=list)
    segment_id: int = 0  # los parciales sucesivos de un mismo tramo comparten segment_id; el final lo cierra
    stable_upto: int = 0  # nº de palabras iniciales que el motor ya no va a cambiar (acuerdo local)
    ts: dict[str, float] = Field(default_factory=dict)  # reloj monotónico del servidor, ms


# ------------------------------------------------------------------ comprensión
class EntityMention(BaseModel):
    type: Literal["player", "team", "coach", "referee"]
    id: str
    span: tuple[int, int]  # [inicio, fin) en tokens normalizados
    surface: str
    score: float = 1.0
    via: EntityVia = "exact"


class NluEvent(BaseModel):
    type: EventType
    fine: str
    modality: Modality = "real"
    roles: dict[Role, str] = Field(default_factory=dict)  # Role -> id canónico
    span: tuple[int, int] = (0, 0)
    chain: Optional[str] = None
    order: int = 0
    confidence: float = 1.0

    def target(self) -> Optional[str]:
        for r in TARGET_ROLES:
            if r in self.roles:
                return self.roles[r]
        return None

    def key(self) -> tuple[str, str, Optional[str], Optional[str]]:
        """Tupla con la que se puntúa en make eval."""
        return (self.type, self.modality, self.roles.get("actor") or self.roles.get("team_for"), self.target())


class Intent(BaseModel):
    type: Literal["stat_query", "compare", "show"]
    topic: Optional[str] = None
    subject: Optional[str] = None
    other: Optional[str] = None


class NluResult(BaseModel):
    trace_id: str = ""
    text: str
    t0: float = 0.0
    t1: float = 0.0
    final: bool = True
    entities: list[EntityMention] = Field(default_factory=list)
    events: list[NluEvent] = Field(default_factory=list)
    intents: list[Intent] = Field(default_factory=list)
    low_confidence: bool = False
    ts: dict[str, float] = Field(default_factory=dict)


# ------------------------------------------------------------------ partido
class MatchEvent(BaseModel):
    id: str
    t_audio: float
    minute: Optional[int] = None
    period: Optional[int] = None
    type: EventType
    fine: str = ""
    roles: dict[Role, str] = Field(default_factory=dict)
    team: Optional[str] = None
    source: Literal["nlu", "operator", "feed"] = "nlu"
    status: Literal["auto", "approved", "edited", "discarded"] = "auto"
    confidence: float = 1.0
    text: str = ""
    trace_id: str = ""


class GraphicCommand(BaseModel):
    id: str
    kind: GraphicKind
    priority: int = 50
    ttl_ms: int = 12000
    pinned: bool = False
    reason: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    demo_data: bool = True
    ts: dict[str, float] = Field(default_factory=dict)


class StageTiming(BaseModel):
    trace_id: str
    stage: Literal["asr", "nlu", "select", "net", "paint", "total"]
    ms: float


# ------------------------------------------------------------------ datos
class Player(BaseModel):
    id: str
    team: str
    name: str
    known_as: str
    number: Optional[int] = None
    position: Position
    line: Line
    foot: Literal["L", "R", "B"] = "R"
    born: Optional[int] = None
    academy: bool = False
    nationality: str = ""
    aliases: list[str] = Field(default_factory=list)
    asr_aliases: list[str] = Field(default_factory=list)
    epithets: list[str] = Field(default_factory=list)


class Team(BaseModel):
    id: str
    name: str
    short: str
    aliases: list[str] = Field(default_factory=list)
    colors: dict[str, str] = Field(default_factory=dict)
    coach: Optional[str] = None
    stadium: Optional[str] = None


class StandingRow(BaseModel):
    pos: int
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    points: int
    form: list[Literal["W", "D", "L"]] = Field(default_factory=list)


class MatchInfo(BaseModel):
    id: str
    season: str
    round: int
    date: str
    home: str
    away: str
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    synthetic: bool = False  # el resultado es real (openfootball) aunque los eventos sean sintéticos


class PitchEvent(BaseModel):
    """Evento con coordenadas (105×68, el equipo del jugador ataca hacia x creciente)."""
    id: int
    match: str
    team: str
    player: str
    minute: int
    second: int = 0
    type: Literal["pass", "shot", "dribble", "recovery", "foul", "card", "sub", "tackle", "interception",
                  "clearance", "save", "carry", "touch"]
    x: float
    y: float
    end_x: Optional[float] = None
    end_y: Optional[float] = None
    outcome: Optional[str] = None  # pass: complete|incomplete; shot: goal|saved|off|blocked|post; ...
    receiver: Optional[str] = None
    xg: Optional[float] = None
    key_pass: bool = False
    assist: bool = False
    body: Optional[str] = None
    detail: Optional[str] = None  # card: yellow|red; sub: jugador que sale; ...


class StatValue(BaseModel):
    value: float
    per90: Optional[float] = None
    percentile: Optional[int] = None  # frente a jugadores de su misma posición con minutos suficientes


class PlayerSeason(BaseModel):
    player: str
    season: str
    matches: int
    starts: int
    minutes: int
    stats: dict[str, StatValue]  # goals, assists, xg, xa, shots, shots_on_target, passes, pass_pct, key_passes,
    # dribbles, dribbles_won, recoveries, tackles, interceptions, fouls, fouled, yellow, red, saves, ...
    synthetic: bool = True


class TeamSeason(BaseModel):
    team: str
    season: str
    stats: dict[str, StatValue]
    synthetic: bool = True


class PassNode(BaseModel):
    player: str
    x: float
    y: float
    passes: int
    touches: int


class PassEdge(BaseModel):
    a: str
    b: str
    count: int  # a -> b


class PassNetwork(BaseModel):
    team: str
    scope: str  # id de partido o temporada
    nodes: list[PassNode]
    edges: list[PassEdge]
    synthetic: bool = True


class Connection(BaseModel):
    a: str
    b: str
    season: str
    a_to_b: int
    b_to_a: int
    key_passes: int
    assists: int
    rank_for_a: int  # posición de b entre los destinatarios de a
    sample: list[PitchEvent] = Field(default_factory=list)  # pases representativos para dibujar
    synthetic: bool = True


class H2H(BaseModel):
    a: str
    b: str
    played: int
    a_wins: int
    draws: int
    b_wins: int
    a_goals: int
    b_goals: int
    last: list[MatchInfo] = Field(default_factory=list)
