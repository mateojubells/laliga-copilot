import { useEffect, useState } from "react";

type Row = { n: number; p50: number; p95: number };
const STAGES: [string, string][] = [
  ["asr", "Voz (fin de palabra → texto)"], ["nlu", "Comprensión"], ["select", "Selección"], ["net", "Red / toma"],
  ["paint", "Pintado"], ["total", "Total"],
];

export function LatencyPanel() {
  const [open, setOpen] = useState(false);
  const [lat, setLat] = useState<Record<string, Row>>({});
  const [errors, setErrors] = useState<number | null>(null);
  useEffect(() => {
    if (!open) return;
    let alive = true;
    const load = () =>
      fetch("/api/metrics")
        .then((r) => (r.ok ? r.json() : null))
        .then((m) => { if (alive && m) { setLat(m.latency ?? {}); setErrors(m.status?.errors ?? 0); } })
        .catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, [open]);
  return (
    <details className="op-latency" open={open} onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>Latencias</summary>
      <table data-testid="latency-table">
        <thead><tr><th>Etapa</th><th>n</th><th>p50 ms</th><th>p95 ms</th></tr></thead>
        <tbody>
          {STAGES.map(([k, label]) => {
            const r = lat[k];
            return (
              <tr key={k} className={k === "total" ? "tot" : ""}>
                <td>{label}</td>
                <td className="num">{r?.n ?? "—"}</td>
                <td className="num">{r ? Math.round(r.p50) : "—"}</td>
                <td className="num">{r ? Math.round(r.p95) : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {errors != null && <p className="op-dim">Errores del servidor: {errors}</p>}
    </details>
  );
}
