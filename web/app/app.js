const $ = id => document.getElementById(id);
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const estrellas = e => "★".repeat(Math.round(e)) + "☆".repeat(5 - Math.round(e));

/* ---------- Navegación entre vistas (#chat, #ranking, #malla) ---------- */
const VISTAS = ["chat", "ranking", "malla"];
function ruta() {
  const h = (location.hash || "#chat").slice(1), v = VISTAS.includes(h) ? h : "chat";
  VISTAS.forEach(id => $(id).hidden = id !== v);
  document.querySelectorAll("nav a").forEach(a =>
    a.dataset.vista === v ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
}
addEventListener("hashchange", ruta);

/* ---------- Chat simulado: las respuestas son de ejemplo ---------- */
const PLANES = [
  {nombre:"Plan A: mejores profesores", sacrifica:"un hueco de 3 horas los martes y jueves",
   clases:[
    {m:"Análisis de algoritmos", p:"Dra. Hernández", e:4.7, d:["L","I"],     h:[9,11],  cr:8},
    {m:"Cálculo diferencial",    p:"Mtra. Ortega",   e:4.9, d:["M","J"],     h:[8,10],  cr:8},
    {m:"Bases de datos",         p:"Dr. Villalobos", e:4.1, d:["M","J"],     h:[13,15], cr:8},
    {m:"Física general",         p:"Dr. Medina",     e:4.4, d:["V"],         h:[9,12],  cr:8}]},
  {nombre:"Plan B: sin huecos", sacrifica:"Estructuras de datos con un profesor de 3.2 estrellas",
   clases:[
    {m:"Análisis de algoritmos", p:"Dra. Hernández", e:4.7, d:["L","I"],     h:[9,11],  cr:8},
    {m:"Cálculo diferencial",    p:"Mtra. Ortega",   e:4.9, d:["M","J"],     h:[9,11],  cr:8},
    {m:"Estructuras de datos",   p:"Mtro. Salazar",  e:3.2, d:["M","J"],     h:[11,13], cr:8},
    {m:"Física general",         p:"Dr. Medina",     e:4.4, d:["V"],         h:[9,12],  cr:8}]},
];
const EJEMPLOS = ["24 a 32 créditos, clases de 8:00 a 14:00",
                  "Sin huecos entre materias y con buenos profesores",
                  "Evita profesores con menos de 3.5 estrellas"];
const DIAS = ["L", "M", "I", "J", "V"];   // L M I J V, como en SIIAU

function pintaHorario(i) {
  const p = PLANES[i];
  let g = DIAS.map((d, k) => `<div class="dia" style="grid-column:${k + 2};grid-row:1">${d}</div>`).join("");
  for (let x = 7; x < 20; x++) g += `<div class="hora" style="grid-column:1;grid-row:${x - 5}">${x}:00</div>`;
  p.clases.forEach((c, k) => c.d.forEach(d => g +=
    `<div class="bloque c${k % 4}" style="grid-column:${DIAS.indexOf(d) + 2};grid-row:${c.h[0] - 5}/${c.h[1] - 5}">
       <strong>${c.m}</strong><br>${c.p} · ${c.e}★</div>`));
  const cr = p.clases.reduce((s, c) => s + c.cr, 0);
  $("panel").innerHTML = `<p><strong>${p.nombre}</strong> · ${cr} créditos</p>
    <p class="sac">Se sacrifica: ${p.sacrifica}.</p><div class="horario">${g}</div>`;
}

function agrega(clase, html) {
  const d = document.createElement("div");
  d.className = "msg " + clase; d.innerHTML = html;
  $("mensajes").appendChild(d); $("mensajes").scrollTop = $("mensajes").scrollHeight;
}
function enviar(texto) {
  texto = texto.trim(); if (!texto) return;
  agrega("yo", `<p>${esc(texto)}</p>`); $("texto").value = "";
  setTimeout(() => agrega("bot",
    `<p>Armé dos planes. Cada uno sacrifica algo distinto:</p>` +
    PLANES.map((p, i) => `<div class="plan"><strong>${p.nombre}</strong>
      <p class="sac">Se sacrifica: ${p.sacrifica}.</p>
      <button class="btn" type="button" data-plan="${i}">Ver horario</button></div>`).join("")), 500);
}
$("mensajes").addEventListener("click", e => {
  const b = e.target.closest("[data-plan]"); if (b) pintaHorario(+b.dataset.plan);
});
$("enviar").addEventListener("click", () => enviar($("texto").value));
$("texto").addEventListener("keydown", e => { if (e.key === "Enter") enviar($("texto").value); });
$("ejemplos").innerHTML = EJEMPLOS.map(t => `<button type="button">${t}</button>`).join("");
$("ejemplos").addEventListener("click", e => { if (e.target.tagName === "BUTTON") enviar(e.target.textContent); });

/* ---------- Ranking de profesores ---------- */
DEPARTAMENTOS.forEach(d => $("r-depto").add(new Option(d, d)));
function pintaRanking() {
  const q = $("r-materia").value.toLowerCase(), d = $("r-depto").value, asc = $("r-orden").value === "asc";
  const l = PROFESORES.filter(p => p.m.toLowerCase().includes(q) && (!d || p.d === d))
                      .sort((a, b) => asc ? a.e - b.e : b.e - a.e);
  $("r-lista").innerHTML = l.length ? l.map(p => `<tr><td>${p.n}</td><td>${p.d}</td><td>${p.m}</td>
    <td><span class="estrellas">${estrellas(p.e)}</span> ${p.e.toFixed(1)}</td><td>${p.r}</td></tr>`).join("")
    : `<tr><td colspan="5">Ningún profesor coincide. Prueba con otra materia o departamento.</td></tr>`;
}
["r-materia", "r-depto", "r-orden"].forEach(id => $(id).addEventListener("input", pintaRanking));

/* ---------- Malla curricular ---------- */
CARRERAS.forEach(c => $("m-carrera").add(new Option(c.nombre, c.id)));
[1, 2, 3, 4].forEach(n => $("m-ciclo").add(new Option("Ciclo " + n, n)));
function pintaMalla() {
  const c = CARRERAS.find(x => x.id === $("m-carrera").value), ciclo = $("m-ciclo").value,
        q = $("m-texto").value.toLowerCase();
  const l = c.materias.filter(m => (!ciclo || m[0] == ciclo) && (m[1] + " " + m[2]).toLowerCase().includes(q));
  $("m-lista").innerHTML = l.length ? l.map(m => `<tr>${m.map(v => `<td>${v}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="5">No hay materias con esos filtros.</td></tr>`;
}
["m-carrera", "m-ciclo", "m-texto"].forEach(id => $(id).addEventListener("input", pintaMalla));

ruta(); pintaRanking(); pintaMalla();
