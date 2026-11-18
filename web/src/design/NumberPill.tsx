import type { CSSProperties } from "react";
import "./Tiles.css";

/**
 * Dorsal en píldora del color del club: la única "cara" del jugador cuando no hay foto (regla "foto o nada": sin siluetas).
 * Por defecto toma `--club-fill` / `--club-ink` del panel; para un rival se pasan sus colores.
 */
export function NumberPill({ number, fill, ink, className }: { number: number | string; fill?: string; ink?: string; className?: string }) {
  const style = fill ? ({ "--club-fill": fill, "--club-ink": ink ?? "#fff" } as CSSProperties) : undefined;
  return (
    <span className={`num-pill display num${className ? ` ${className}` : ""}`} style={style} data-testid="num-pill">
      {number}
    </span>
  );
}
