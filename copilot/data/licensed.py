"""Hueco documentado para datos de pago (Opta / StatsBomb / API-Football). Todos los métodos lanzan NotImplementedError.

Qué haría falta para cada proveedor
-----------------------------------
Opta (Stats Perform, feed F24 eventos + F1/F9 resultados + F40 plantillas)
    * Licencia comercial con derechos de emisión; la clave y los endpoints se dan con el contrato.
    * F24 (eventos con x,y en % de campo 0-100, `type_id`: 1 pase, 13-16 tiros, 3 regate, 4 falta, 7 entrada, 8 intercepción,
      12 despeje, 10 parada, 17 tarjeta, 18/19 cambio): convertir a PitchEvent escalando x*1.05, y*0.68. Opta orienta
      cada equipo hacia x creciente en cada parte; coincide con nuestra convención por equipo.
    * Mapeo de ids: tabla `opta_team_id -> slug` y `opta_player_id -> equipo/slug` (data/rosters/2024-25.json);
      xG viene en el qualifier 321 (xG) y 322 (xGOT); asistencia = qualifier 210; pase clave = 29.
StatsBomb (Open Data gratis para competiciones sueltas; API de pago para LaLiga completa)
    * Open data: https://github.com/statsbomb/open-data (licencia propia: exige atribución y no es uso comercial libre
      sin acuerdo). API: /events/{match_id}, /matches/{competition_id}/{season_id}, /lineups/{match_id}, con usuario y clave.
    * Campo 120x80, origen arriba-izquierda: x*105/120, y = 68 - y*68/80. xG en `shot.statsbomb_xg`.
      `pass.shot_assist` / `pass.goal_assist` -> key_pass / assist.
API-Football (api-sports.io)
    * Plan gratuito limitado y sin la temporada en curso; de pago desde ~15 USD/mes. Cabecera `x-apisports-key`.
    * Endpoints: /fixtures?league=140&season=2024, /fixtures/events?fixture=, /fixtures/players?fixture=,
      /players?league=140&season=2024, /standings. Solo trae eventos de alto nivel (goles, tarjetas, cambios) sin
      coordenadas: sirve para player_season/standings/h2h, no para pass_network/connection/shot_map.
Común
    * Respetar `until` (solo lo ocurrido antes del partido/jornada indicados) en todos los agregados.
    * Mapear siempre a los ids canónicos de docs/ARCHITECTURE.md §4 y devolver `synthetic=False` en los modelos.
    * Cachear en disco la respuesta cruda: las cuotas de API y las licencias penalizan las lecturas repetidas.
"""
from __future__ import annotations

from typing import Optional

from copilot.types import (H2H, Connection, MatchInfo, PassNetwork, PitchEvent, Player, PlayerSeason, StandingRow,
                           Team, TeamSeason)

_MSG = "LicensedProvider: sin credenciales ni mapeo de ids; ver el docstring del módulo"


class LicensedProvider:
    synthetic = False

    def __init__(self, provider: str = "opta", api_key: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key

    def teams(self, season: str) -> list[Team]:
        raise NotImplementedError(_MSG)

    def squad(self, team_id: str, season: str) -> list[Player]:
        raise NotImplementedError(_MSG)

    def standings(self, season: str, until_round: Optional[int] = None) -> list[StandingRow]:
        raise NotImplementedError(_MSG)

    def matches(self, season: str, team_id: Optional[str] = None) -> list[MatchInfo]:
        raise NotImplementedError(_MSG)

    def player_season(self, player_id: str, season: str, *, until=None) -> PlayerSeason:
        raise NotImplementedError(_MSG)

    def team_season(self, team_id: str, season: str, *, until=None) -> TeamSeason:
        raise NotImplementedError(_MSG)

    def events(self, match_id=None, *, player_id=None, team_id=None, types=None, season=None,
               until=None) -> list[PitchEvent]:
        raise NotImplementedError(_MSG)

    def pass_network(self, team_id: str, *, match_id=None, season=None, until=None) -> PassNetwork:
        raise NotImplementedError(_MSG)

    def connection(self, a: str, b: str, *, season: str, until=None) -> Connection:
        raise NotImplementedError(_MSG)

    def h2h(self, team_a: str, team_b: str, *, until=None) -> H2H:
        raise NotImplementedError(_MSG)
