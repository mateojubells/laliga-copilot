import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MatchState } from "../contracts";
import { initialState } from "../live/reducer";
import { EndMatch } from "../live/ui/EndMatch";
import { MatchClock } from "../live/ui/MatchClock";
import { ScoreEditor } from "../live/ui/ScoreEditor";
import type { LiveState, OperatorAction } from "../live/types";
import { Operator } from "./Operator";

class FakeWS {
  static all: FakeWS[] = [];
  readyState = 0;
  binaryType = "";
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  constructor(public url: string) { FakeWS.all.push(this); }
  send(_data?: unknown) {}
  close() { this.readyState = 3; }
}

const team = (id: string) => ({ id, name: id, short: id.slice(0, 3).toUpperCase(), colors: {}, crest: "" });
const match = (extra: Partial<MatchState> = {}): MatchState => ({ match: "m", home: team("barca"), away: team("valla"), ...extra });
const st = (m: MatchState | null): LiveState => ({ ...initialState(), match: m });

function mockFetch(session: unknown, ok = true) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (String(url).startsWith("/api/session")) return { ok, status: ok ? 200 : 500, json: async () => session } as Response;
    return { ok: false, status: 404, json: async () => ({}) } as Response;
  }));
}

beforeEach(() => { FakeWS.all = []; vi.stubGlobal("WebSocket", FakeWS); });
afterEach(() => { vi.unstubAllGlobals(); });

const app = () => render(
  <MemoryRouter initialEntries={["/"]}>
    <Routes>
      <Route path="/" element={<Operator />} />
      <Route path="/setup" element={<div data-testid="setup-page" />} />
    </Routes>
  </MemoryRouter>,
);

describe("ruta / (operador)", () => {
  it("sin partido en curso (config null) redirige a /setup", async () => {
    mockFetch({ config: null });
    app();
    expect(await screen.findByTestId("setup-page")).toBeInTheDocument();
  });

  it("con partido en curso enseña el operador con la barra nueva", async () => {
    mockFetch({ config: { season: "2024-25", match: "x", lineups: {}, voice: "mic" } });
    app();
    expect(await screen.findByTestId("operator")).toBeInTheDocument();
    expect(screen.getByTestId("op-clock")).toBeInTheDocument();
    expect(screen.getByTestId("op-panic")).toBeInTheDocument();
    expect(screen.getByTestId("op-voice")).toBeInTheDocument();
    expect(screen.getByTestId("op-program-chip")).toHaveTextContent("Sin salida de programa");
  });

  it("si el servidor no responde no redirige: enseña el operador con aviso y reintenta", async () => {
    mockFetch({}, false);
    app();
    expect(await screen.findByRole("alert")).toHaveTextContent(/No se pudo comprobar/);
    expect(screen.queryByTestId("setup-page")).toBeNull();
  });

  it("Mayús+Esc envía pánico", async () => {
    mockFetch({ config: { season: "s", match: "x", lineups: {} } });
    app();
    await screen.findByTestId("operator");
    const ws = FakeWS.all[FakeWS.all.length - 1];
    const sent: string[] = [];
    ws.send = (s: unknown) => { sent.push(String(s)); };
    ws.readyState = 1;
    act(() => { ws.onopen?.(); });
    fireEvent.keyDown(window, { key: "Escape", shiftKey: true });
    expect(sent.some((s) => JSON.parse(s).type === "panic")).toBe(true);
  });
});

describe("reloj en la barra", () => {
  const send = () => { const f = vi.fn<(a: OperatorAction) => boolean>(() => true); return f; };

  it("antes del partido el botón es «Pitido inicial» y envía kickoff", () => {
    const s = send();
    render(<MatchClock state={st(match({ period: 0 }))} send={s} serverNow={() => 0} />);
    fireEvent.click(screen.getByTestId("op-clock-btn"));
    expect(screen.getByTestId("op-clock-btn")).toBeTruthy();
    expect(s).toHaveBeenCalledWith({ type: "clock", value: "kickoff" });
  });

  it("pinta el minuto:segundo a partir del estado y el reloj del servidor, con +N de descuento", () => {
    render(<MatchClock state={st(match({ period: 1, clock_running: true, clock_base_s: 2700, clock_at_ms: 1000, added: 3 }))} send={send()} serverNow={() => 1000 + 65_000} />);
    expect(screen.getByTestId("op-clock-time")).toHaveTextContent("46:05");
    expect(screen.getByTestId("op-clock-added")).toHaveTextContent("+3");
    expect(screen.getByTestId("op-clock-phase")).toHaveTextContent("1.ª parte");
    expect(screen.getByTestId("op-clock-btn")).toHaveTextContent("Descanso");
  });

  it("«Final» pide confirmación en la interfaz antes de enviar", () => {
    const s = send();
    render(<MatchClock state={st(match({ period: 2, clock_running: true, clock_base_s: 5000, clock_at_ms: 0 }))} send={s} serverNow={() => 0} />);
    fireEvent.click(screen.getByTestId("op-clock-btn"));
    expect(s).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("op-clock-confirm"));
    expect(s).toHaveBeenCalledWith({ type: "clock", value: "full_time" });
  });

  it("ajustar minuto y descuento envía set_minute y set_added", () => {
    const s = send();
    render(<MatchClock state={st(match({ period: 1, clock_running: true, clock_base_s: 600, clock_at_ms: 0, added: 1 }))} send={s} serverNow={() => 0} />);
    fireEvent.click(screen.getByText("Ajustar"));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "23" } });
    fireEvent.click(screen.getByText("Fijar"));
    expect(s).toHaveBeenCalledWith({ type: "clock", value: "set_minute", event: { minute: 23, second: 0 } });
    fireEvent.click(screen.getByText("Ajustar"));
    fireEvent.click(screen.getByLabelText("Añadir un minuto de descuento"));
    expect(s).toHaveBeenCalledWith({ type: "clock", value: "set_added", event: { minutes: 2 } });
  });
});

describe("marcador editable", () => {
  it("clic, +/− por equipo y Aplicar envía set_score", () => {
    const s = vi.fn<(a: OperatorAction) => boolean>(() => true);
    render(<ScoreEditor match={match({ home_goals: 1, away_goals: 0 })} send={s} />);
    fireEvent.click(screen.getByTestId("op-score"));
    fireEvent.click(screen.getByLabelText("Añadir un gol a BAR"));
    fireEvent.click(screen.getByLabelText("Añadir un gol a VAL"));
    fireEvent.click(screen.getByText("Aplicar"));
    expect(s).toHaveBeenCalledWith({ type: "set_score", event: { home: 2, away: 1 } });
  });
});

describe("terminar partido", () => {
  it("confirma en la interfaz, pita el final si falta, hace DELETE y avisa", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => { calls.push(`${init?.method ?? "GET"} ${url}`); return { ok: true, status: 200, json: async () => ({ config: null }) } as Response; }));
    const s = vi.fn<(a: OperatorAction) => boolean>(() => true);
    const ended = vi.fn();
    render(<EndMatch state={st(match({ period: 2, clock_running: true }))} send={s} onEnded={ended} />);
    fireEvent.click(screen.getByTestId("op-end"));
    expect(calls).toEqual([]);
    fireEvent.click(screen.getByTestId("op-end-confirm"));
    await waitFor(() => expect(ended).toHaveBeenCalled());
    expect(s).toHaveBeenCalledWith({ type: "clock", value: "full_time" });
    expect(calls).toEqual(["DELETE /api/session"]);
  });

  it("si el partido ya está en Final no vuelve a mandar full_time", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }) as Response));
    const s = vi.fn<(a: OperatorAction) => boolean>(() => true);
    render(<EndMatch state={st(match({ period: 3 }))} send={s} onEnded={() => undefined} />);
    fireEvent.click(screen.getByTestId("op-end"));
    fireEvent.click(screen.getByTestId("op-end-confirm"));
    await waitFor(() => expect(s).toHaveBeenCalledWith({ type: "voice", value: "stop" }));
    expect(s).not.toHaveBeenCalledWith({ type: "clock", value: "full_time" });
  });
});
