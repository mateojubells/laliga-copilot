import { describe, expect, it } from "vitest";
import type { MatchState } from "../contracts";
import { ClockSync } from "./clock";
import { clockSeconds, fmtMatchClock, periodControl, phaseOf } from "./matchClock";

const team = (id: string) => ({ id, name: id, short: id.slice(0, 3).toUpperCase(), colors: {}, crest: "" });
const ms = (extra: Partial<MatchState> = {}): MatchState => ({ match: "m", home: team("a"), away: team("b"), ...extra });

describe("reloj del partido", () => {
  it("corriendo: base + tiempo transcurrido desde clock_at_ms", () => {
    const m = ms({ period: 1, clock_running: true, clock_base_s: 600, clock_at_ms: 100_000 });
    expect(clockSeconds(m, 100_000)).toBe(600);
    expect(clockSeconds(m, 163_500)).toBe(663.5);
    expect(fmtMatchClock(clockSeconds(m, 163_500))).toBe("11:03");
  });

  it("parado: no avanza; sin sincronía de reloj enseña la base", () => {
    expect(clockSeconds(ms({ clock_running: false, clock_base_s: 2700, clock_at_ms: 5 }), 99_999)).toBe(2700);
    expect(clockSeconds(ms({ clock_running: true, clock_base_s: 30, clock_at_ms: 5 }), null)).toBe(30);
    expect(clockSeconds(null, 1)).toBe(0);
  });

  it("usa el desfase de ClockSync: serverNow = performance.now() + offset", () => {
    const sync = new ClockSync();
    // el cliente envió en 1000 y recibió en 1040 (rtt 40); el servidor decía 50_000 → offset = 50000 − 1020
    sync.add(1000, 50_000, 1040);
    const m = ms({ period: 2, clock_running: true, clock_base_s: 2700, clock_at_ms: 49_000 });
    // en el cliente performance.now() = 2020 → servidor = 51_000 → 2 s después del ancla
    expect(clockSeconds(m, sync.serverTime(2020))).toBeCloseTo(2702, 6);
  });

  it("no retrocede si el ancla es ligeramente futura (jitter)", () => {
    const m = ms({ clock_running: true, clock_base_s: 100, clock_at_ms: 10_050 });
    expect(clockSeconds(m, 10_000)).toBe(100);
  });

  it("formato: minutos sin límite de 59", () => {
    expect(fmtMatchClock(0)).toBe("00:00");
    expect(fmtMatchClock(5703)).toBe("95:03");
  });
});

describe("fase y botón contextual", () => {
  const cases: [string, MatchState | null, string, string | null][] = [
    ["sin estado", null, "pre", "Pitido inicial"],
    ["previa", ms({ period: 0 }), "pre", "Pitido inicial"],
    ["1.ª parte", ms({ period: 1, clock_running: true, clock_base_s: 10 }), "first", "Descanso"],
    ["descanso (period 1 parado)", ms({ period: 1, clock_running: false, clock_base_s: 2700 }), "half", "Inicio 2.ª parte"],
    ["descanso (period 2 aún en 45:00)", ms({ period: 2, clock_running: false, clock_base_s: 2700 }), "half", "Inicio 2.ª parte"],
    ["2.ª parte", ms({ period: 2, clock_running: true, clock_base_s: 2700 }), "second", "Final"],
    ["final", ms({ period: 3, clock_running: false, clock_base_s: 5400 }), "final", null],
  ];
  it.each(cases)("%s", (_n, m, phase, label) => {
    expect(phaseOf(m)).toBe(phase);
    expect(periodControl(m)?.label ?? null).toBe(label);
  });

  it("sólo «Final» pide confirmación y envía el valor correcto", () => {
    expect(periodControl(ms({ period: 0 }))).toMatchObject({ value: "kickoff", confirm: false });
    expect(periodControl(ms({ period: 1, clock_running: true, clock_base_s: 5 }))).toMatchObject({ value: "half_time", confirm: false });
    expect(periodControl(ms({ period: 2, clock_running: true, clock_base_s: 2800 }))).toMatchObject({ value: "full_time", confirm: true });
  });
});
