"""CompositeProvider: resultados, clasificación y h2h REALES (openfootball) + todo lo demás sintético.

`synthetic = True` siempre (la interfaz muestra "Datos de demostración"). Si el SQLite sintético de una temporada no
existe, sigue funcionando con lo real (teams, squad, matches, standings, h2h) y `available()` devuelve False; los
métodos que necesitan eventos lanzan SyntheticDataMissing (RuntimeError) con la instrucción `make data`.

Temporadas: cada llamada se resuelve con su `season` (o la temporada de `match_id`/`until`); si no hay ninguna,
con la del constructor (`season=`) y, si tampoco, con seasons.current(). Se crea un SyntheticProvider por temporada
(base `seasons.synth_db(temporada)`), perezosamente.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from copilot import seasons
from copilot.data.openfootball import OpenFootballProvider, parse_until
from copilot.data.synthetic import SyntheticProvider


class CompositeProvider:
    synthetic = True

    def __init__(self, real: Optional[OpenFootballProvider] = None, synth: Optional[SyntheticProvider] = None,
                 db_path: Path | str | None = None, season: Optional[str] = None):
        self.real = real or OpenFootballProvider()
        self._fixed = synth  # proveedor sintético único (se usa para cualquier temporada)
        self._db_path = Path(db_path) if db_path else None
        self.season = season
        self._synths: dict[str, SyntheticProvider] = {}

    # ------------------------------------------------------------- resolución de temporada
    def _season(self, season: Optional[str] = None, match_id: Optional[str] = None, until=None) -> str:
        if season:
            return season
        if match_id:
            return seasons.season_of(match_id)
        if until is not None:
            c = parse_until(until, self.season or seasons.current())
            if c:
                return c[0]
        return self.season or seasons.current()

    def synth_for(self, season: Optional[str] = None) -> SyntheticProvider:
        if self._fixed is not None:
            return self._fixed
        season = season or self.season or seasons.current()
        if season not in self._synths:
            explicit = self._db_path is not None and season == (self.season or seasons.current())
            self._synths[season] = SyntheticProvider(self._db_path if explicit else None, season=season)
        return self._synths[season]

    @property
    def synth(self) -> SyntheticProvider:
        """Proveedor sintético de la temporada por defecto."""
        return self.synth_for(None)

    def available(self, season: Optional[str] = None) -> bool:
        """True si hay datos sintéticos de eventos de esa temporada (el SQLite generado)."""
        return self.synth_for(season).available()

    # ---- reales
    def teams(self, season):
        return self.real.teams(season)

    def matches(self, season, team_id=None):
        return self.real.matches(season, team_id)

    def standings(self, season, until_round=None):
        return self.real.standings(season, until_round)

    def h2h(self, team_a, team_b, *, until=None):
        return self.real.h2h(team_a, team_b, until=until)

    # ---- sintéticos
    def squad(self, team_id, season):
        return self.synth_for(season).squad(team_id, season)

    def player_season(self, player_id, season, *, until=None):
        return self.synth_for(season).player_season(player_id, season, until=until)

    def team_season(self, team_id, season, *, until=None):
        return self.synth_for(season).team_season(team_id, season, until=until)

    def events(self, match_id=None, *, player_id=None, team_id=None, types=None, season=None, until=None):
        return self.synth_for(self._season(season, match_id, until)).events(
            match_id, player_id=player_id, team_id=team_id, types=types, season=season, until=until)

    def pass_network(self, team_id, *, match_id=None, season=None, until=None):
        return self.synth_for(self._season(season, match_id, until)).pass_network(
            team_id, match_id=match_id, season=season, until=until)

    def connection(self, a, b, *, season, until=None):
        return self.synth_for(season).connection(a, b, season=season, until=until)
