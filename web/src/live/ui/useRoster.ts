import { useEffect, useMemo, useState } from "react";
import type { PlayerRef, TeamRef } from "../../contracts";

export interface Roster {
  teams: TeamRef[];
  players: PlayerRef[];
  playerName: (id: string | undefined) => string;
  teamShort: (id: string | null | undefined) => string;
  teamOfPlayer: (id: string) => string | undefined;
}

/** GET /api/roster (equipos y jugadores del partido). Reintenta cada 3 s hasta tenerlo. */
export function useRoster(): Roster {
  const [data, setData] = useState<{ teams: TeamRef[]; players: PlayerRef[] }>({ teams: [], players: [] });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () =>
      fetch("/api/roster")
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((d) => { if (alive) setData(d); })
        .catch(() => { if (alive) timer = setTimeout(load, 3000); });
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, []);
  return useMemo(() => {
    const p = new Map(data.players.map((x) => [x.id, x]));
    const t = new Map(data.teams.map((x) => [x.id, x]));
    return {
      ...data,
      playerName: (id) => (id ? p.get(id)?.known_as ?? id.split("/").pop() ?? id : "—"),
      teamShort: (id) => (id ? t.get(id)?.short ?? id : ""),
      teamOfPlayer: (id) => p.get(id)?.team.id,
    };
  }, [data]);
}
