import { act, render, screen } from "@testing-library/react";
import { MotionGlobalConfig } from "framer-motion";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FIXTURES } from "../fixtures";
import { Program, fitScale } from "./Program";

class FakeWS {
  static all: FakeWS[] = [];
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  constructor(public url: string) { FakeWS.all.push(this); }
  send(s: string) { this.sent.push(JSON.parse(s)); }
  close() { this.readyState = 3; }
  open() { this.readyState = 1; this.onopen?.(); }
  emit(m: Record<string, unknown>) { this.onmessage?.({ data: JSON.stringify({ server_now: 5000, ...m }) }); }
  drop() { this.readyState = 3; this.onclose?.(); }
}

const graphic = (id: string, extra: Record<string, unknown> = {}) => ({ id, kind: "player_card", priority: 70, ttl_ms: 5000, payload: FIXTURES.player_card, demo_data: true, ...extra });
const mount = (url = "/program") => render(<MemoryRouter initialEntries={[url]}><Program /></MemoryRouter>);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date", "requestAnimationFrame", "cancelAnimationFrame"] });
  MotionGlobalConfig.skipAnimations = true;
  FakeWS.all = [];
  vi.stubGlobal("WebSocket", FakeWS);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  MotionGlobalConfig.skipAnimations = false;
});

const sock = () => FakeWS.all[FakeWS.all.length - 1];
const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

describe("Program", () => {
  it("se conecta como role=program y pide la sincronía de reloj", () => {
    mount();
    expect(sock().url).toContain("/ws?role=program");
    act(() => sock().open());
    expect(sock().sent[0]).toMatchObject({ type: "ping" });
  });

  it("pinta el grafismo recibido, informa de que se ha pintado y lo retira al vencer su ttl", async () => {
    const { container } = mount();
    act(() => sock().open());
    act(() => sock().emit({ type: "program", graphic: graphic("g-1") }));
    expect(container.querySelector('[data-kind="player_card"]')).not.toBeNull();
    await advance(50); // dos requestAnimationFrame
    expect(sock().sent.find((m) => m.type === "painted")).toMatchObject({ graphic_id: "g-1" });
    await advance(4000);
    expect(container.querySelector('[data-kind="player_card"]')).not.toBeNull();
    await advance(1100);
    expect(container.querySelector('[data-kind="player_card"]')).toBeNull();
  });

  it("un grafismo fijado no caduca; program_clear lo quita", async () => {
    const { container } = mount();
    act(() => sock().open());
    act(() => sock().emit({ type: "program", graphic: graphic("g-2", { pinned: true }) }));
    await advance(60_000);
    expect(container.querySelector('[data-kind="player_card"]')).not.toBeNull();
    act(() => sock().emit({ type: "program_clear" }));
    await advance(10);
    expect(container.querySelector('[data-kind="player_card"]')).toBeNull();
  });

  it("muestra el marcador permanente desde 'state' y se puede ocultar con ?scorebug=0", () => {
    const state = { match: "m", home: FIXTURES.scorebug.home, away: FIXTURES.scorebug.away, home_goals: 1, away_goals: 0, period: 1, minute: 23 };
    const a = mount();
    act(() => sock().open());
    act(() => sock().emit({ type: "state", state }));
    expect(a.container.querySelector('[data-kind="scorebug"]')).not.toBeNull();
    a.unmount();
    const b = mount("/program?scorebug=0");
    act(() => sock().open());
    act(() => sock().emit({ type: "state", state }));
    expect(b.container.querySelector('[data-kind="scorebug"]')).toBeNull();
  });

  it("si el socket se cae reintenta sin mostrar ningún error", async () => {
    const { container } = mount();
    act(() => sock().open());
    const n = FakeWS.all.length;
    act(() => sock().drop());
    await advance(600);
    expect(FakeWS.all.length).toBe(n + 1);
    expect(container.textContent).toBe("");
    expect(screen.queryByText(/error|conexi/i)).toBeNull();
  });

  it("?scale=1 no escala y ?bg=green pone el croma", () => {
    const { getByTestId } = mount("/program?scale=1&bg=green");
    expect(getByTestId("program-canvas").style.transform).toBe("scale(1)");
    expect(getByTestId("program-root").dataset.bg).toBe("green");
    expect(fitScale(960, 540)).toBe(0.5);
    expect(fitScale(1920, 400)).toBeCloseTo(400 / 1080);
  });
});
