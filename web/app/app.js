const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const estrellas = e => "★".repeat(Math.round(e)) + "☆".repeat(5 - Math.round(e));

/* Calificaciones de SIIAPP: nombre del profesor, tal como sale en el catálogo -> estrellas.
   Por ahora está vacío. Ej.: {"VERA SORIA, FRANCISCO": 4.5} */
const ESTRELLAS = {};

/* Catálogo real (catalogo.json) y reseñas de estudiantes (resenas.json) */
let CATALOGO = [];
let RESENAS = [];
const POR = new Map();
const cargado = Promise.all([
  fetch("catalogo.json").then(r => r.json()).then(d => { CATALOGO = d; }).catch(() => {}),
  fetch("resenas.json").then(r => r.json()).then(d => {
    RESENAS = d; d.forEach(r => POR.set(r.k, [...(POR.get(r.k) || []), r]));
  }).catch(() => {})   // si el archivo no existe, la página funciona sin reseñas
]);

/* ---------- Navegación entre vistas (#chat, #ranking, #malla) ---------- */
const VISTAS = ["chat", "ranking", "malla"];
function ruta() {
  const h = (location.hash || "#chat").slice(1), v = VISTAS.includes(h) ? h : "chat";
  VISTAS.forEach(id => $(id).hidden = id !== v);
  document.querySelectorAll("nav a").forEach(a =>
    a.dataset.vista === v ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
}
addEventListener("hashchange", ruta);

/* ---------- Utilidades de horario ---------- */
const DIAS = ["L", "M", "I", "J", "V", "S"];            // como en SIIAU
const aMin = h => { const [a, b] = h.split(":"); return +a * 60 + +b; };
const rango = h => h.split("-").map(aMin);               // "13:00-14:55" -> [780, 895]
const fmt = m => `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
function choca(a, b) {
  if (!a.dias.some(d => b.dias.includes(d))) return false;
  const [s1, e1] = rango(a.hora), [s2, e2] = rango(b.hora);
  return s1 < e2 && s2 < e1;
}

/* Armado de ejemplo (voraz simple). El armado real lo hace el algoritmo de K.A.T.E. */
function armaPlan(pool, orden, tope) {
  const clases = [], claves = new Set(); let cr = 0;
  for (const c of [...pool].sort(orden)) {
    if (claves.has(c.clave) || cr + c.creditos > tope) continue;
    if (clases.some(e => choca(e, c))) continue;
    clases.push(c); claves.add(c.clave); cr += c.creditos;
  }
  return {clases, cr};
}

let ultimos = [];
function pintaHorario(i) {
  const p = ultimos[i];
  let g = DIAS.map((d, k) => `<div class="dia" style="grid-column:${k + 2};grid-row:1">${d}</div>`).join("");
  for (let h = 7; h < 21; h++) g += `<div class="hora" style="grid-column:1;grid-row:${(h - 7) * 2 + 2}/span 2">${h}:00</div>`;
  p.clases.forEach((c, k) => {
    const [s, e] = rango(c.hora);
    const r1 = Math.max(2, Math.floor((s - 420) / 30) + 2), r2 = Math.min(30, Math.ceil((e - 420) / 30) + 2);
    c.dias.forEach(d => { if (DIAS.includes(d)) g +=
      `<div class="bloque c${k % 4}" style="grid-column:${DIAS.indexOf(d) + 2};grid-row:${r1}/${r2}">
         <strong>${esc(c.materia)}</strong><br>${c.hora} · NRC ${c.nrc}</div>`; });
  });
  $("panel").innerHTML = `<p><strong>${p.nombre}</strong> · ${p.cr} créditos · ${p.clases.length} materias</p>
    <p class="sac">Se sacrifica: ${p.sacrifica}.</p>
    <p class="vacio">NRC: ${p.clases.map(c => c.nrc).join(", ")}</p><div class="horario">${g}</div>`;
}

/* ---------- Chat ---------- */
const EJEMPLOS = ["24 a 32 créditos, clases de 8:00 a 14:00",
                  "Sin huecos entre materias",
                  "16 créditos, clases de 10:00 a 18:00"];
function agrega(clase, html) {
  const d = document.createElement("div");
  d.className = "msg " + clase; d.innerHTML = html;
  $("mensajes").appendChild(d); $("mensajes").scrollTop = $("mensajes").scrollHeight;
}
function enviar(texto) {
  texto = texto.trim(); if (!texto) return;
  agrega("yo", `<p>${esc(texto)}</p>`); $("texto").value = "";
  if (!CATALOGO.length) {
    agrega("bot", "<p>No pude cargar el catálogo. Si abriste el archivo con doble clic, el navegador lo bloquea: usa la página publicada.</p>");
    return;
  }
  const cm = texto.match(/(\d+)(?:\s*a\s*(\d+))?\s*cr/i), tope = cm ? +(cm[2] || cm[1]) : 24;
  const vm = texto.match(/(\d{1,2}):\d\d\s*(?:a|-)\s*(\d{1,2}):\d\d/), v = vm ? [+vm[1] * 60, +vm[2] * 60] : [420, 1260];
  const pool = CATALOGO.filter(c => c.disponibles > 0 && c.hora && c.dias.length &&
                                    rango(c.hora)[0] >= v[0] && rango(c.hora)[1] <= v[1]);
  const A = armaPlan(pool, (a, b) => rango(a.hora)[0] - rango(b.hora)[0], tope);
  const B = armaPlan(pool, (a, b) => b.disponibles - a.disponibles, tope);
  const tiempos = p => p.clases.flatMap(c => rango(c.hora));
  A.nombre = "Plan A: clases más temprano";
  A.sacrifica = `cupo justo, la sección con menos lugares tiene ${Math.min(...A.clases.map(c => c.disponibles))} disponibles`;
  B.nombre = "Plan B: más cupo disponible";
  B.sacrifica = `horario más disperso, de ${fmt(Math.min(...tiempos(B)))} a ${fmt(Math.max(...tiempos(B)))}`;
  ultimos = [A, B].filter(p => p.clases.length);
  if (!ultimos.length) { agrega("bot", "<p>No encontré secciones con cupo que cumplan eso. Prueba con un rango de horas más amplio.</p>"); return; }
  agrega("bot", `<p>Demostración: armé ${ultimos.length} plan(es) con secciones reales del ciclo ${esc(CATALOGO[0].ciclo)}. Cada uno sacrifica algo distinto:</p>` +
    ultimos.map((p, i) => `<div class="plan"><strong>${p.nombre}</strong>
      <p class="sac">Se sacrifica: ${p.sacrifica}.</p>
      <button class="btn" type="button" data-plan="${i}">Ver horario</button></div>`).join(""));
}
$("mensajes").addEventListener("click", e => {
  const b = e.target.closest("[data-plan]"); if (b) pintaHorario(+b.dataset.plan);
});
$("enviar").addEventListener("click", () => enviar($("texto").value));
$("texto").addEventListener("keydown", e => { if (e.key === "Enter") enviar($("texto").value); });
$("ejemplos").innerHTML = EJEMPLOS.map(t => `<button type="button">${t}</button>`).join("");
$("ejemplos").addEventListener("click", e => { if (e.target.tagName === "BUTTON") enviar(e.target.textContent); });

/* ---------- Ranking de profesores (catálogo real + reseñas) ---------- */
const norm = s => String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().replace(/\s+/g, " ").trim();
const resenasDe = n => POR.get(norm(n)) || [];
const nombreMateria = cl => { for (const c of CARRERAS) for (const m of c.materias) if (m[1] === cl) return m[2]; return cl; };
function pintaRanking() {
  document.querySelector("#ranking thead").innerHTML =
    "<tr><th>Profesor</th><th>Materias</th><th>Secciones</th><th>Calificación</th><th>Acerca del profesor</th></tr>";
  $("r-depto").parentElement.style.display = "none";    // el catálogo no trae departamento
  if (!CATALOGO.length) { $("r-lista").innerHTML = `<tr><td colspan="5">No se pudo cargar el catálogo.</td></tr>`; return; }
  const q = $("r-materia").value.toLowerCase(), asc = $("r-orden").value === "asc", m = new Map();
  CATALOGO.forEach(c => (c.profesores || [c.profesor]).filter(Boolean).forEach(n => {
    const o = m.get(n) || {n, materias: new Set(), sec: 0};
    o.materias.add(c.materia); o.sec++; m.set(n, o);
  }));
  const e = p => ESTRELLAS[p.n], rv = p => resenasDe(p.n).length;
  const l = [...m.values()].filter(p => !q || [...p.materias].some(x => x.toLowerCase().includes(q)))
    .sort((a, b) => e(a) == null || e(b) == null
      ? (e(a) == null) - (e(b) == null) || rv(b) - rv(a) || a.n.localeCompare(b.n)
      : asc ? e(a) - e(b) : e(b) - e(a));
  $("r-lista").innerHTML = l.length ? l.map(p => {
    const ms = [...p.materias], rs = resenasDe(p.n);
    return `<tr><td>${esc(p.n)}</td><td>${esc(ms.slice(0, 3).join(", "))}${ms.length > 3 ? ` (+${ms.length - 3})` : ""}</td>
      <td>${p.sec}</td><td>${e(p) != null ? `<span class="estrellas">${estrellas(e(p))}</span> ${e(p).toFixed(1)}` : "Sin calificación"}</td>
      <td>${rs.length ? `<button class="btn" type="button" data-acerca>Acerca del profesor (${rs.length})</button>` : "Sin reseñas"}</td></tr>
      ${rs.length ? `<tr class="acerca" hidden><td colspan="5">${rs.map(r =>
        `<p><strong>${esc(nombreMateria(r.c))}</strong> (${r.c})<br>${esc(r.t)}</p>`).join("")}
        <p class="vacio">Opiniones de estudiantes recopiladas por Acción U (ciclo 2026A); no son calificaciones oficiales.</p></td></tr>` : ""}`;
  }).join("") : `<tr><td colspan="5">Ningún profesor coincide. Prueba con otra materia.</td></tr>`;
}
$("r-lista").addEventListener("click", ev => {
  const b = ev.target.closest("[data-acerca]");
  if (b) { const r = b.closest("tr").nextElementSibling; r.hidden = !r.hidden; }
});
["r-materia", "r-orden"].forEach(id => $(id).addEventListener("input", pintaRanking));

/* ---------- Malla curricular (datos.js) cruzada con el catálogo ---------- */
CARRERAS.forEach(c => $("m-carrera").add(new Option(c.nombre, c.id)));
function llenaSemestres() {
  const c = CARRERAS.find(x => x.id === $("m-carrera").value);
  const sems = [...new Set(c.materias.map(m => m[0]))].sort((a, b) => a - b);
  $("m-ciclo").innerHTML = '<option value="">Todos</option>' +
    sems.map(s => `<option value="${s}">${s > 9 ? "Optativas" : "Semestre " + s}</option>`).join("");
}
function pintaMalla() {
  const c = CARRERAS.find(x => x.id === $("m-carrera").value), sem = $("m-ciclo").value,
        q = $("m-texto").value.toLowerCase();
  const l = c.materias.filter(m => (!sem || m[0] == sem) && (m[1] + " " + m[2]).toLowerCase().includes(q));
  const n = k => k ? CATALOGO.filter(x => x.clave === k).length : 0;   // secciones en el catálogo
  $("m-lista").innerHTML = l.length ? l.map(m => `<tr><td>${m[0] > 9 ? "Opt." : m[0]}</td><td>${esc(m[1] || "—")}</td>
      <td>${esc(m[2])}</td><td>${m[3]}</td><td>${n(m[1]) || "—"}</td></tr>`).join("")
    : `<tr><td colspan="5">No hay materias con esos filtros.</td></tr>`;
}
$("m-carrera").addEventListener("input", () => { llenaSemestres(); pintaMalla(); });
["m-ciclo", "m-texto"].forEach(id => $(id).addEventListener("input", pintaMalla));

llenaSemestres();
pintaMalla();
ruta();
cargado.then(() => { pintaRanking(); pintaMalla(); });
