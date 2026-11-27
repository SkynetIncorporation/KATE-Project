/* Cliente del chat hacia el proxy (worker/index.js). Si falla, app.js usa el análisis por regex. */
const GEMINI_PROXY_URL = "https://kate-gemini-proxy.skynetkate.workers.dev";

async function interpretaConGemini(texto) {
  try {
    const r = await fetch(GEMINI_PROXY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto }),
      signal: AbortSignal.timeout(60000)   // con el backend MCP el modelo puede hacer varias llamadas
    });
    if (!r.ok) return null;
    const d = await r.json();
    const hora = h => (typeof h === "string" && /^\d{1,2}:\d\d$/.test(h)) ? h : null;
    const cr = Number.isFinite(d.creditos_max) ? Math.min(Math.max(d.creditos_max, 1), 60) : null;
    // Planes que armó el algoritmo vía el backend MCP (solo si vienen bien formados).
    const planes = Array.isArray(d.planes) ? d.planes.filter(p =>
      p && Array.isArray(p.nrcs) && p.nrcs.every(n => typeof n === "string")).slice(0, 3).map(p => ({
      nombre: typeof p.nombre === "string" ? p.nombre : "Plan",
      nrcs: p.nrcs,
      creditos_total: Number.isFinite(p.creditos_total) ? p.creditos_total : null,
      sacrifica: typeof p.sacrifica === "string" ? p.sacrifica : ""
    })) : [];
    return {
      planes,
      creditos_max: cr,
      hora_inicio: hora(d.hora_inicio),
      hora_fin: hora(d.hora_fin),
      respuesta: typeof d.respuesta === "string" ? d.respuesta : ""
    };
  } catch { return null; }   // el modelo solo propone; la página valida todo antes de usarlo
}
