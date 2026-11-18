import { describe, expect, it } from "vitest";
import type { PlayerRef, TeamLineup } from "../contracts";
import { buildChecks, canStart, type CheckInput } from "./checks";
import { clickMove, movePlayer, slotOf, validateLineup } from "./lineup";
import { replayAvailable } from "../routes/Setup";

const T = { id: "t", name: "T", short: "T", colors: {}, crest: "" };
const pl = (id: string, position: PlayerRef["position"]): PlayerRef => ({ id, name: id, known_as: id, position, line: position === "GK" ? "GK" : "MID", team: T, avatar: "" });
const squad = [pl("gk1", "GK"), pl("gk2", "GK"), ...Array.from({ length: 14 }, (_, i) => pl(`p${i}`, "CM"))];
const base = (): TeamLineup => ({ starting: ["gk1", ...Array.from({ length: 10 }, (_, i) => `p${i}`)], bench: ["gk2", "p10", "p11"] });

describe("validación de alineaciones", () => {
  it("11 titulares con 1 portero es válida", () => {
    expect(validateLineup(base(), squad)).toMatchObject({ ok: true, starters: 11, keepers: 1, errors: [] });
  });
  it("10 titulares: error con el recuento", () => {
    const r = validateLineup(movePlayer(base(), "p0", "bench"), squad);
    expect(r.ok).toBe(false);
    expect(r.errors[0]).toMatch(/10 titulares/);
  });
  it("sin portero o con dos porteros no vale", () => {
    const noGk = validateLineup(movePlayer(movePlayer(base(), "gk1", "bench"), "p10", "starting"), squad);
    expect(noGk.keepers).toBe(0);
    expect(noGk.errors.join(" ")).toMatch(/Falta el portero/);
    const two = validateLineup(movePlayer(movePlayer(base(), "p0", "bench"), "gk2", "starting"), squad);
    expect(two.keepers).toBe(2);
    expect(two.errors.join(" ")).toMatch(/2 porteros/);
  });
  it("12 titulares tampoco", () => {
    expect(validateLineup(movePlayer(base(), "p10", "starting"), squad).ok).toBe(false);
  });
});

describe("mover jugadores", () => {
  it("clic: titular → banquillo → titular; no convocado → banquillo", () => {
    let l = clickMove(base(), "p0");
    expect(slotOf(l, "p0")).toBe("bench");
    l = clickMove(l, "p0");
    expect(slotOf(l, "p0")).toBe("starting");
    expect(slotOf(clickMove(base(), "p13"), "p13")).toBe("bench");
  });
  it("movePlayer nunca duplica y permite 'no convocado'", () => {
    const l = movePlayer(base(), "p11", "out");
    expect(slotOf(l, "p11")).toBe("out");
    const all = [...l.starting, ...l.bench];
    expect(new Set(all).size).toBe(all.length);
    expect(base().bench).toContain("p11"); // no muta la entrada
  });
});

const input = (o: Partial<CheckInput> = {}): CheckInput => ({
  serverOk: true, seasonHasResults: true, matchChosen: true, lineupErrors: [], lineupsLoaded: true,
  voice: "mic", micPeak: 0.4, micTooQuiet: false, programClients: 1, ...o,
});

describe("comprobación previa", () => {
  it("todo en verde permite empezar", () => {
    const c = buildChecks(input());
    expect(c.map((x) => x.id)).toEqual(["server", "season", "lineups", "mic", "program"]);
    expect(canStart(c)).toBe(true);
  });
  it("servidor caído o alineación inválida bloquean", () => {
    expect(canStart(buildChecks(input({ serverOk: false })))).toBe(false);
    expect(canStart(buildChecks(input({ lineupErrors: ["x"] })))).toBe(false);
    expect(canStart(buildChecks(input({ matchChosen: false, lineupsLoaded: false })))).toBe(false);
  });
  it("micro sin probar, señal baja y programa sin conectar avisan pero no bloquean", () => {
    const c = buildChecks(input({ micPeak: null, programClients: 0 }));
    expect(c.find((x) => x.id === "mic")?.status).toBe("warn");
    expect(c.find((x) => x.id === "program")?.status).toBe("warn");
    expect(canStart(c)).toBe(true);
    expect(canStart(buildChecks(input({ micTooQuiet: true })))).toBe(true);
  });
  it("sin micro elegido no hay check de micro", () => {
    expect(buildChecks(input({ voice: "none" })).some((x) => x.id === "mic")).toBe(false);
  });
});

describe("repetición de prueba", () => {
  it("sólo 2024-25 / J04 / Barcelona–Valladolid", () => {
    expect(replayAvailable("2024-25", { id: "2024-25/j04/barcelona-valladolid", round: 4 })).toBe(true);
    expect(replayAvailable("2024-25", { id: "2024-25/j05/barcelona-getafe", round: 5 })).toBe(false);
    expect(replayAvailable("2025-26", { id: "x/barcelona-valladolid", round: 4 })).toBe(false);
    expect(replayAvailable("2024-25", null)).toBe(false);
  });
});
