import type { CSSProperties } from "react";
import { PERCENTILE_SHOW_FROM, PercentileBar } from "./PercentileBar";
import "./Tiles.css";

export interface StatTileProps {
  label: string;
  /** Valor ya formateado ("0,62", "87 %"). */
  value: string;
  percentile?: number | null;
  /** false = sin barra de percentil aunque haya dato (fichas de equipo). */
  bar?: boolean;
  /** El dato que motivó el grafismo. */
  highlight?: boolean;
  /** Texto pequeño bajo la cifra ("0,41 por 90'"). */
  sub?: string | null;
  /** Filete lateral de 6 px de este color (tile neutra que se reconoce con su flecha del campo). */
  edge?: string;
}

/** Cifra grande (72 px) + etiqueta (24 px) + barra "TOP x %" solo si el percentil es 75 o más. La destacada es un bloque del color del club. */
export function StatTile({ label, value, percentile, bar = true, highlight, sub, edge }: StatTileProps) {
  return (
    <div
      className={`stat-tile${highlight ? " stat-tile--hl" : ""}${edge ? " stat-tile--edge" : ""}`}
      style={edge ? ({ "--edge": edge } as CSSProperties) : undefined}
      data-testid="stat-tile"
    >
      <div className="stat-tile__label caps">{label}</div>
      <div className="stat-tile__value display num">{value}</div>
      {sub && <div className="stat-tile__sub">{sub}</div>}
      {bar && percentile != null && percentile >= PERCENTILE_SHOW_FROM && <PercentileBar percentile={percentile} />}
    </div>
  );
}
