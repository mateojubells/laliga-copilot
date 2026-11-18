import { useCallback, useEffect, useRef, useState } from "react";
import { isTooQuiet, levelToMeter } from "../live/audio/meter";
import { MicCapture, MicError, listMicDevices, loadMicDevice, micFailureText, saveMicDevice, type MicDevice } from "../live/audio/mic";

export interface MicTestResult { peak: number }

/** Selector de dispositivo + medidor en vivo (calculado en el navegador) + prueba de 5 s con nivel máximo. */
export function MicTest({ onResult }: { onResult: (r: MicTestResult | null) => void }) {
  const [devices, setDevices] = useState<MicDevice[]>([]);
  const [device, setDevice] = useState(loadMicDevice());
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [left, setLeft] = useState(0); // segundos que faltan de la prueba (0 = no hay prueba)
  const [result, setResult] = useState<number | null>(null);
  const capRef = useRef<MicCapture | null>(null);
  const maxRef = useRef(0);
  const testingRef = useRef(false);
  // el permiso del micro solo se pide cuando el operador lo decide, nunca al abrir el menú
  const [armed, setArmed] = useState(false);

  const open = useCallback(async (id: string) => {
    capRef.current?.stop(); capRef.current = null;
    setError(null); setLevel(0);
    const cap = new MicCapture();
    try {
      await cap.start({
        deviceId: id || undefined,
        onChunk: (_pcm, peak) => { setLevel(levelToMeter(peak)); if (testingRef.current && peak > maxRef.current) maxRef.current = peak; },
        onLost: () => setError(micFailureText("lost")),
      });
      capRef.current = cap;
      // las etiquetas sólo existen con el permiso concedido: se listan ahora
      setDevices(await listMicDevices());
    } catch (e) {
      cap.stop();
      setError(e instanceof MicError ? e.message : micFailureText("other"));
    }
  }, []);

  useEffect(() => {
    if (!armed) return;
    void open(device);
    return () => { capRef.current?.stop(); capRef.current = null; };
    // al activar y al cambiar de dispositivo
  }, [armed, device, open]);

  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => {
      if (left === 1) {
        testingRef.current = false;
        setResult(maxRef.current);
        onResult({ peak: maxRef.current });
      }
      setLeft(left - 1);
    }, 1000);
    return () => clearTimeout(t);
  }, [left, onResult]);

  const probe = () => {
    maxRef.current = 0; testingRef.current = true; setResult(null); onResult(null); setLeft(5);
  };
  const pick = (id: string) => { saveMicDevice(id); setDevice(id); setResult(null); onResult(null); };
  const pct = Math.round(level * 100);

  if (!armed) {
    return (
      <div className="su-mic">
        <div className="su-row">
          <button type="button" className="su-btn" onClick={() => setArmed(true)} data-testid="su-mic-arm">Activar micrófono</button>
          <span className="su-dim">El navegador te pedirá permiso para usar el micrófono de este Mac.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="su-mic">
      <label className="su-field">Dispositivo de entrada
        <select value={device} onChange={(e) => pick(e.target.value)} data-testid="su-mic-device">
          <option value="">Predeterminado del sistema</option>
          {devices.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
        </select>
      </label>
      <div className="su-meter-row">
        <div className="su-meter" role="meter" aria-label="Nivel del micrófono" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <i style={{ width: `${pct}%` }} className={level > 0.92 ? "hot" : ""} />
        </div>
        <span className="su-dim num">{pct}%</span>
      </div>
      <div className="su-row">
        <button type="button" className="su-btn" onClick={probe} disabled={left > 0 || !!error} data-testid="su-mic-probe">
          {left > 0 ? `Probando… ${left} s` : "Probar 5 s"}
        </button>
        <span className="su-dim">Di algo como «gol de Lewandowski» con tu voz normal de comentarista.</span>
      </div>
      {result != null && (
        <p className={`su-note ${isTooQuiet(result) ? "warn" : "ok"}`} role="status" data-testid="su-mic-result">
          Nivel máximo: <b>{Math.round(levelToMeter(result) * 100)}%</b>{" "}
          {isTooQuiet(result) ? "— demasiado bajo: acércate al micro, sube la ganancia de entrada o elige otro dispositivo." : "— correcto."}
        </p>
      )}
      {error && <p className="su-note bad" role="alert">{error}</p>}
    </div>
  );
}
