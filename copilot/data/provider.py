"""Capa única de acceso a datos (docs/ARCHITECTURE.md §6).

Implementaciones: synthetic.py (datos de demostración generados), openfootball.py (resultados reales, gratis),
licensed.py (hueco documentado para Opta / StatsBomb / API-Football).
"""
from __future__ import annotations

from typing import Optional, Protocol, Union, runtime_checkable

from copilot.types import (H2H, Connection, MatchInfo, PassNetwork, PitchEvent, Player, PlayerSeason,
                           StandingRow, Team, TeamSeason)


#: Corte temporal: id de partido ("2024-25/J04/barcelona-valladolid") o nº de jornada. Los agregados solo cuentan
#: lo ocurrido ANTES de ese partido/jornada (en directo en la J4 no se enseñan datos de la J30). None = todo.
Until = Optional[Union[str, int]]


@runtime_checkable
class DataProvider(Protocol):
    synthetic: bool  # True → la interfaz muestra "Datos de demostración"

    def teams(self, season: str) -> list[Team]: ...
    def squad(self, team_id: str, season: str) -> list[Player]: ...
    def standings(self, season: str, until_round: Optional[int] = None) -> list[StandingRow]: ...
    def matches(self, season: str, team_id: Optional[str] = None) -> list[MatchInfo]: ...
    def player_season(self, player_id: str, season: str, *, until: Until = None) -> PlayerSeason: ...
    def team_season(self, team_id: str, season: str, *, until: Until = None) -> TeamSeason: ...
    def events(self, match_id: Optional[str] = None, *, player_id: Optional[str] = None,
               team_id: Optional[str] = None, types: Optional[list[str]] = None,
               season: Optional[str] = None, until: Until = None) -> list[PitchEvent]: ...
    def pass_network(self, team_id: str, *, match_id: Optional[str] = None,
                     season: Optional[str] = None, until: Until = None) -> PassNetwork: ...
    def connection(self, a: str, b: str, *, season: str, until: Until = None) -> Connection: ...
    def h2h(self, team_a: str, team_b: str, *, until: Until = None) -> H2H: ...


@runtime_checkable
class ImageProvider(Protocol):
    def player_avatar(self, player_id: str, *, size: int = 512) -> str: ...  # SVG
    def team_crest(self, team_id: str, *, size: int = 256) -> str: ...  # SVG
