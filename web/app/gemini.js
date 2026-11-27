/* Cliente del chat hacia el proxy (worker/index.js). Si falla, app.js usa el análisis por regex. */
const GEMINI_PROXY_URL = "https://kate-gemini-proxy.skynetkate.workers.dev";

async function interpretaConGemini(texto) {
  try {
    const r = await fetch(GEMINI_PROXY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto }),
      signal: AbortSignal.timeout(15000)
    });
    if (!r.ok) return null;
    const d = await r.json();
    const hora = h => (typeof h === "string" && /^\d{1,2}:\d\d$/.test(h)) ? h : null;
    const cr = Number.isFinite(d.creditos_max) ? Math.min(Math.max(d.creditos_max, 1), 60) : null;
    return {
      creditos_max: cr,
      hora_inicio: hora(d.hora_inicio),
      hora_fin: hora(d.hora_fin),
      respuesta: typeof d.respuesta === "string" ? d.respuesta : ""
    };
  } catch { return null; }   // el modelo solo propone; la página valida todo antes de usarlo
}
