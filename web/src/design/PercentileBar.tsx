import "./Tiles.css";

/** Barra 0-100 con la etiqueta en lenguaje de antena ("TOP 3 %", no "P97"). El relleno es neutro (blanco): el color queda para la tile del club. */
export function PercentileBar({ percentile, label = true }: { percentile: number; label?: boolean }) {
  const p = Math.max(0, Math.min(100, Math.round(percentile)));
  return (
    <div
      className="pbar"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={p}
      aria-label={`Percentil ${p}`}
      data-testid="percentile-bar"
    >
      <div className="pbar__track">
        <div className="pbar__fill" style={{ width: `${p}%` }} />
      </div>
      {label && <span className="pbar__label num display">TOP {Math.max(1, 100 - p)} %</span>}
    </div>
  );
}

/** Por debajo de este percentil no se enseña barra: si no hay nada que presumir, no se enseña. */
export const PERCENTILE_SHOW_FROM = 75;
