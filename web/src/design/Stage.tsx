import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

export const CANVAS_W = 1920;
export const CANVAS_H = 1080;

/**
 * Lienzo lógico 1920×1080 escalado con transform: scale al ancho disponible.
 * Los hijos se diseñan en px lógicos; aquí nunca se recalcula maquetación.
 * `fit="width"` escala según el ancho del contenedor; el contenedor impone 16:9.
 */
export function Stage({
  children,
  className,
  style,
  fixedScale,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  /** Fuerza una escala (tests, /program a tamaño nativo). */
  fixedScale?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(fixedScale ?? 1);

  useEffect(() => {
    if (fixedScale != null) return;
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const w = el.getBoundingClientRect().width;
      if (w > 0) setScale(w / CANVAS_W);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [fixedScale]);

  return (
    <div
      ref={ref}
      className={className}
      data-testid="stage"
      style={{ position: "relative", width: "100%", aspectRatio: "16 / 9", overflow: "hidden", ...style }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: CANVAS_W,
          height: CANVAS_H,
          transform: `scale(${scale})`,
          transformOrigin: "0 0",
        }}
      >
        {children}
      </div>
    </div>
  );
}
