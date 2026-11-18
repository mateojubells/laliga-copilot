import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LineupProposal, MatchListItem, PlayerRef } from "../contracts";
import { Setup } from "./Setup";

class FakeWS {
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  constructor(public url: string) {}
  send() {}
  close() { this.readyState = 3; }
}

const T = (id: string) => ({ id, name: id, short: id.slice(0, 3).toUpperCase(), colors: { primary: "#123456" }, crest: "" });
const player = (team: string, i: number, position: PlayerRef["position"]): PlayerRef => ({
  id: `${team}/p${i}`, name: `P${i}`, known_as: `${team}${i}`, number: i, position, line: position === "GK" ? "GK" : "MID", team: T(team), avatar: "",
});
const squad = (team: string) => [player(team, 1, "GK"), ...Array.from({ length: 13 }, (_, i) => player(team, i + 2, "CM"))];
const lu = (team: string) => ({ starting: squad(team).slice(0, 11).map((p) => p.id), bench: squad(team).slice(11).map((p) => p.id) });
const M: MatchListItem = { id: "2024-25/j04/barcelona-valladolid", season: "2024-25", round: 4, date: "2024-09-15", home: T("barcelona"), away: T("valladolid"), home_goals: 7, away_goals: 0, has_lineup: true };
const proposal: LineupProposal = { match: M.id, source: "saved", teams: { barcelona: lu("barcelona"), valladolid: lu("valladolid") }, squads: { barcelona: squad("barcelona"), valladolid: squad("valladolid") } };

let posted: unknown = null;
let sessionBody: unknown = { config: null };
let postStatus = 200;

beforeEach(() => {
  posted = null; sessionBody = { config: null }; postStatus = 200;
  vi.stubGlobal("WebSocket", FakeWS);
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    const res = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as Response;
    if (u === "/api/seasons") return res([{ season: "2024-25", teams: 20, players: 500, has_results: true, has_stats: true, current: true }]);
    if (u.startsWith("/api/matches")) return res([M]);
    if (u.startsWith("/api/lineup")) return res(proposal);
    if (u === "/api/session" && init?.method === "POST") { posted = JSON.parse(String(init.body)); return postStatus === 200 ? res({ config: posted }) : res({ detail: "Alineación no válida: falta el portero" }, postStatus); }
    if (u === "/api/session") return res(sessionBody);
    return res({}, 404);
  }));
  // sin getUserMedia: el paso de micro enseña su error, que no debe romper nada
  Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });
});
afterEach(() => vi.unstubAllGlobals());

const mount = () => render(
  <MemoryRouter initialEntries={["/setup"]}>
    <Routes>
      <Route path="/setup" element={<Setup />} />
      <Route path="/" element={<div data-testid="operator-page" />} />
    </Routes>
  </MemoryRouter>,
);

describe("/setup", () => {
  it("flujo completo: temporada → partido → alineaciones → Empezar → POST y navega a /", async () => {
    mount();
    fireEvent.click(await screen.findByTestId("su-season-2024-25"));
    fireEvent.click(await screen.findByTestId(`su-match-${M.id}`));
    expect(await screen.findByTestId("su-valid-barcelona")).toHaveTextContent("11 titulares y portero");
    fireEvent.click(screen.getByTestId("su-voice-none"));
    await waitFor(() => expect(screen.getByTestId("su-start")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("su-start"));
    expect(await screen.findByTestId("operator-page")).toBeInTheDocument();
    expect(posted).toMatchObject({ season: "2024-25", match: M.id, voice: "none", auto_program: false });
    expect((posted as { lineups: Record<string, { starting: string[] }> }).lineups.barcelona.starting).toHaveLength(11);
  });

  it("una alineación con 10 titulares se marca en rojo y bloquea «Empezar»; restablecer la arregla", async () => {
    mount();
    fireEvent.click(await screen.findByTestId(`su-match-${M.id}`));
    await screen.findByTestId("su-valid-barcelona");
    fireEvent.click(screen.getByTestId("su-pl-barcelona/p5")); // un titular al banquillo
    expect(screen.getByTestId("su-valid-barcelona")).toHaveTextContent(/10 titulares/);
    expect(screen.getByTestId("su-start")).toBeDisabled();
    fireEvent.click(screen.getByTestId("su-reset"));
    expect(screen.getByTestId("su-valid-barcelona")).toHaveTextContent("11 titulares y portero");
  });

  it("la repetición de prueba sólo se habilita con Barça–Valladolid de la J04 de 2024-25", async () => {
    mount();
    expect(await screen.findByTestId("su-voice-replay")).toBeDisabled();
    fireEvent.click(await screen.findByTestId(`su-match-${M.id}`));
    await waitFor(() => expect(screen.getByTestId("su-voice-replay")).not.toBeDisabled());
  });

  it("muestra el error 400 del servidor al empezar", async () => {
    postStatus = 400;
    mount();
    fireEvent.click(await screen.findByTestId(`su-match-${M.id}`));
    await screen.findByTestId("su-valid-barcelona");
    fireEvent.click(screen.getByTestId("su-voice-none"));
    await waitFor(() => expect(screen.getByTestId("su-start")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("su-start"));
    expect(await screen.findByTestId("su-start-error")).toHaveTextContent("falta el portero");
  });

  it("con partido en curso avisa y ofrece continuar o terminar (con confirmación en pantalla)", async () => {
    sessionBody = { config: { season: "2024-25", match: M.id, lineups: {}, voice: "mic" }, home: T("barcelona"), away: T("valladolid"), score: { home: 1, away: 0 } };
    mount();
    expect(await screen.findByTestId("su-running")).toHaveTextContent("Hay un partido en curso");
    fireEvent.click(screen.getByTestId("su-end"));
    fireEvent.click(screen.getByTestId("su-end-confirm"));
    await waitFor(() => expect(screen.queryByTestId("su-running")).toBeNull());
    expect(vi.mocked(fetch).mock.calls.some(([u, i]) => u === "/api/session" && (i as RequestInit)?.method === "DELETE")).toBe(true);
  });

  it("Continuar partido en curso va a /", async () => {
    sessionBody = { config: { season: "2024-25", match: M.id, lineups: {} }, home: T("barcelona"), away: T("valladolid") };
    mount();
    fireEvent.click(await screen.findByTestId("su-continue"));
    expect(await screen.findByTestId("operator-page")).toBeInTheDocument();
  });

  it("si el servidor no responde enseña el error y lo marca en la comprobación previa", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("down"); }));
    mount();
    expect((await screen.findAllByText(/No se puede contactar con el servidor/)).length).toBeGreaterThan(0);
    expect(screen.getByTestId("su-checks")).toHaveTextContent("El servidor responde");
    expect(screen.getByTestId("su-start")).toBeDisabled();
  });
});
