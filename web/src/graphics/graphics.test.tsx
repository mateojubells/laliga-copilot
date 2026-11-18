import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ImageSourceProvider, TeamCrest, PlayerAvatar } from "../design";
import { FIXTURES, LAMINE, BARCELONA, standingsFull, standingsTop } from "../fixtures";
import { Gallery } from "../routes/Gallery";
import { GRAPHICS } from "./registry";
import { PlayerCard } from "./PlayerCard";
import { Standings } from "./Standings";
import { GRAPHIC_KINDS } from "../contracts";

describe("PlayerCard", () => {
  it("muestra el distintivo de demostración cuando demo_data es true", () => {
    render(<PlayerCard payload={FIXTURES.player_card} demoData={true} />);
    const badge = screen.getByTestId("demo-badge");
    expect(badge).toHaveTextContent(/datos de demostración/i);
  });

  it("NO lo muestra cuando demo_data es false", () => {
    render(<PlayerCard payload={FIXTURES.player_card} demoData={false} />);
    expect(screen.queryByTestId("demo-badge")).toBeNull();
    expect(screen.queryByText(/demostración/i)).toBeNull();
  });

  it("pinta nombre, dorsal, titular, 4 tiles con \"TOP x %\" y el dato de hoy en banda propia", () => {
    render(<PlayerCard payload={FIXTURES.player_card} demoData />);
    expect(screen.getByRole("heading", { name: "Lamine Yamal" })).toBeInTheDocument();
    expect(screen.getByText(FIXTURES.player_card.headline!)).toBeInTheDocument();
    expect(screen.getAllByTestId("stat-tile")).toHaveLength(4);
    expect(screen.getAllByTestId("percentile-bar")).toHaveLength(4);
    expect(screen.getByText("TOP 3 %")).toBeInTheDocument();
    expect(screen.getByTestId("pc-today")).toHaveTextContent(/En este partido\s*1\s*gol\s*2\s*tiros\s*3\s*regates/);
    expect(screen.getByText("Extremo derecho")).toBeInTheDocument();
    // sin jerga ni notas de metodología en antena
    expect(screen.queryByText(/Percentil/)).toBeNull();
    expect(screen.queryByText(/\bP\d{2,3}\b/)).toBeNull();
    expect(screen.queryByText(/Extremos de LaLiga/)).toBeNull();
  });

  it("la barra solo se enseña con percentil 75 o más y la destacada nunca se queda fuera de las 4", () => {
    const p = structuredClone(FIXTURES.player_card);
    p.stats = p.stats.map((s) => ({ ...s, highlight: s.key === "pass_pct" }));
    render(<PlayerCard payload={p} demoData />);
    const tiles = screen.getAllByTestId("stat-tile");
    expect(tiles).toHaveLength(4);
    expect(tiles.some((t) => t.className.includes("stat-tile--hl"))).toBe(true);
    expect(screen.getAllByTestId("percentile-bar").length).toBeLessThan(4); // pass_pct es P62: sin barra
  });

  it("omite las barras si el stat no trae percentil", () => {
    const p = structuredClone(FIXTURES.player_card);
    p.stats = p.stats.slice(0, 4).map((s) => ({ ...s, percentile: null, highlight: false }));
    render(<PlayerCard payload={p} demoData />);
    expect(screen.queryAllByTestId("percentile-bar")).toHaveLength(0);
    expect(screen.getAllByTestId("stat-tile")).toHaveLength(4);
  });
});

describe("Standings", () => {
  it("completa: 20 filas en dos columnas con zonas y destacados, sin forma", () => {
    const { container } = render(<Standings payload={standingsFull} demoData />);
    const rows = screen.getAllByTestId("standings-row");
    expect(rows).toHaveLength(20);
    expect(container.querySelectorAll('[role="table"]')).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-zone", "champions");
    expect(rows[19]).toHaveAttribute("data-zone", "relegation");
    expect(within(rows[0]!).getByText("FC Barcelona")).toBeInTheDocument();
    expect(within(rows[0]!).queryAllByText(/^[VED]$/)).toHaveLength(0); // 100 bolitas de forma = confeti
    expect(screen.getByTestId("demo-badge")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /LaLiga/ })).toBeInTheDocument();
  });

  it("ventana (top/around): filas altas con PJ · DG · PTS y la forma en cuadrados", () => {
    const { container } = render(<Standings payload={standingsTop} demoData />);
    expect(screen.getAllByTestId("standings-row")).toHaveLength(8);
    expect(container.querySelectorAll('[role="table"]')).toHaveLength(1);
    expect(container.querySelectorAll(".formdots--sq")).toHaveLength(8);
    expect(container.querySelector(".panel--half")).not.toBeNull();
  });

  it("sin demo no hay distintivo", () => {
    render(<Standings payload={standingsFull} demoData={false} />);
    expect(screen.queryByTestId("demo-badge")).toBeNull();
  });
});

describe("registro de grafismos", () => {
  it("tiene un componente por cada tipo del contrato", () => {
    for (const k of GRAPHIC_KINDS) expect(GRAPHICS[k]).toBeTypeOf("function");
  });
});

describe("escudo y avatar", () => {
  it("modo generated: SVG sin tocar la red", () => {
    render(
      <ImageSourceProvider mode="generated">
        <TeamCrest team={BARCELONA} />
        <PlayerAvatar player={LAMINE} />
      </ImageSourceProvider>,
    );
    expect(screen.getByTestId("crest-generated")).toBeInTheDocument();
    expect(screen.getByTestId("avatar-generated")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("modo remote: intenta la URL y, si falla, cae al SVG generado", () => {
    render(
      <ImageSourceProvider mode="remote">
        <TeamCrest team={BARCELONA} />
        <PlayerAvatar player={LAMINE} />
      </ImageSourceProvider>,
    );
    const imgs = document.querySelectorAll("img");
    expect(imgs).toHaveLength(2);
    expect(imgs[0]!.getAttribute("src")).toBe(BARCELONA.crest);
    imgs.forEach((i) => fireEvent.error(i));
    expect(screen.getByTestId("crest-generated")).toBeInTheDocument();
    expect(screen.getByTestId("avatar-generated")).toBeInTheDocument();
  });
});

describe("Galería", () => {
  it("muestra los 12 tipos + la variante de clasificación", () => {
    render(<MemoryRouter initialEntries={["/gallery"]}><Gallery /></MemoryRouter>);
    expect(screen.getAllByRole("figure")).toHaveLength(13);
  });

  it("?only= aísla un grafismo", () => {
    render(<MemoryRouter initialEntries={["/gallery?only=player_card&bg=green"]}><Gallery /></MemoryRouter>);
    expect(screen.getAllByRole("figure")).toHaveLength(1);
    expect(screen.getByTestId("frame-player_card")).toBeInTheDocument();
    expect(document.querySelector(".g-bg--green")).not.toBeNull();
  });
});
