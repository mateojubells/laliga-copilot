import type { LineupProposal, MatchListItem, SeasonInfoOut, SessionConfig, SessionInfo } from "../contracts";

/** Error de la API con un mensaje que se puede enseñar tal cual (detail del 400, o texto de red). */
export class ApiError extends Error {
  constructor(message: string, readonly status: number = 0) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, init);
  } catch {
    throw new ApiError("No se puede contactar con el servidor.");
  }
  if (!r.ok) {
    let detail = `El servidor respondió ${r.status}.`;
    try {
      const j = (await r.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
      else if (j.detail) detail = JSON.stringify(j.detail);
    } catch { /* cuerpo no JSON */ }
    throw new ApiError(detail, r.status);
  }
  return (await r.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  seasons: () => call<SeasonInfoOut[]>("/api/seasons"),
  matches: (season: string) => call<MatchListItem[]>(`/api/matches?season=${encodeURIComponent(season)}`),
  lineup: (match: string) => call<LineupProposal>(`/api/lineup?match=${encodeURIComponent(match)}`),
  session: () => call<SessionInfo>("/api/session"),
  startSession: (cfg: SessionConfig) => call<SessionInfo>("/api/session", json("POST", cfg)),
  endSession: () => call<SessionInfo>("/api/session", { method: "DELETE" }),
};
