import { createContext, useContext, type ReactNode } from "react";

/**
 * De dónde salen escudos y avatares:
 *  - "generated": SVG generado en cliente (no toca la red; lo usa la galería).
 *  - "remote": se intenta la URL del contrato (/api/img/...) y, si falla, se cae al SVG generado.
 */
export type ImageMode = "generated" | "remote";

const Ctx = createContext<ImageMode>("remote");

export function ImageSourceProvider({ mode, children }: { mode: ImageMode; children: ReactNode }) {
  return <Ctx.Provider value={mode}>{children}</Ctx.Provider>;
}

export const useImageMode = () => useContext(Ctx);
