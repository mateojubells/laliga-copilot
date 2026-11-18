"""ImageProvider propio: avatares y escudos SVG generados (sin fotos ni escudos oficiales: tienen copyright).

Para enchufar imágenes con licencia: implementar la misma interfaz devolviendo el SVG/URL del proveedor contratado
(ver BLOCKERS.md) y cambiar `images.provider` en la configuración.
"""
from __future__ import annotations

from html import escape

from copilot import seasons
from copilot.nlu.gazetteer import season


def _lum(hex_: str) -> float:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


class GeneratedImages:
    def __init__(self) -> None:
        # la temporada activa manda; los equipos/jugadores que solo estén en otras temporadas instaladas también se dibujan
        self.teams = {}
        for name in [seasons.current(), *seasons.installed()]:
            for t in season(name)["teams"]:
                self.teams.setdefault(t["id"], t)
        self.players = {}
        for name in [seasons.current(), *seasons.installed()]:
            for t in season(name)["teams"]:
                for p in t["players"]:
                    self.players.setdefault(p["id"], p)

    def _colors(self, team_id: str) -> tuple[str, str, str]:
        c = self.teams.get(team_id, {}).get("colors", {})
        a, b = c.get("primary", "#334155"), c.get("secondary", "#94a3b8")
        return a, b, "#ffffff" if _lum(a) < 0.6 else "#0b1220"

    def team_crest(self, team_id: str, *, size: int = 256) -> str:
        a, b, ink = self._colors(team_id)
        code = escape((self.teams.get(team_id, {}).get("short") or team_id)[:3].upper())
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 116" width="{size}" height="{int(size * 1.16)}">'
                f'<defs><clipPath id="s"><path d="M6 6h88v58c0 26-22 40-44 46C28 104 6 90 6 64z"/></clipPath></defs>'
                f'<g clip-path="url(#s)"><rect width="100" height="116" fill="{a}"/>'
                f'<rect x="28" width="14" height="116" fill="{b}" opacity=".9"/><rect x="58" width="14" height="116" fill="{b}" opacity=".9"/>'
                f'<rect width="100" height="34" fill="{a}"/></g>'
                f'<path d="M6 6h88v58c0 26-22 40-44 46C28 104 6 90 6 64z" fill="none" stroke="#fff" stroke-opacity=".85" stroke-width="4"/>'
                f'<text x="50" y="27" text-anchor="middle" font-family="Barlow Condensed,Arial Narrow,sans-serif" font-weight="700" '
                f'font-size="19" letter-spacing="1.5" fill="{ink}">{code}</text></svg>')

    def player_avatar(self, player_id: str, *, size: int = 512) -> str:
        p = self.players.get(player_id, {})
        a, b, ink = self._colors(p.get("team", ""))
        num = "" if p.get("number") is None else str(p["number"])
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="{size}" height="{size}">'
                f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{a}"/>'
                f'<stop offset="1" stop-color="{a}" stop-opacity=".55"/></linearGradient><clipPath id="c"><circle cx="100" cy="100" r="96"/></clipPath></defs>'
                f'<circle cx="100" cy="100" r="98" fill="{b}"/><g clip-path="url(#c)"><rect width="200" height="200" fill="url(#g)"/>'
                f'<circle cx="100" cy="78" r="34" fill="#000" fill-opacity=".38"/>'
                f'<path d="M30 210c0-52 30-82 70-82s70 30 70 82z" fill="#000" fill-opacity=".38"/>'
                f'<path d="M78 130l22 20 22-20" fill="none" stroke="{b}" stroke-width="7" stroke-linejoin="round"/></g>'
                f'<text x="100" y="186" text-anchor="middle" font-family="Barlow Condensed,Arial Narrow,sans-serif" font-weight="800" '
                f'font-size="46" fill="#fff" stroke="#000" stroke-opacity=".35" stroke-width="1.5">{escape(num)}</text></svg>')
