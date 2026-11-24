"""Convierte la "Consulta de Oferta Académica" del SIIAU (HTML) en clases_stub.py.

Uso:
    python scripts/importar_siiau.py pagina1.html [pagina2.html ...] -o clases_stub.py

El SIIAU entrega 500 filas por página ("500 Próximos"): pasa todas las páginas
guardadas y se combinan sin duplicar NRC.

Las llaves de cada clase son las del CLASES_STUB original de kate_mcp.py:
ciclo, nrc, clave, materia, seccion, creditos, cupo, disponibles, dias, hora,
edificio, aula, periodo, profesor. Se agregan: profesores, multihorario, sesiones.

Un NRC puede tener varias sesiones (días/horas/aulas distintos), pero las llaves
planas solo admiten una franja, así que se resumen así:
  - dias:    unión de los días de todas las sesiones.
  - hora:    envolvente (primera entrada - última salida) de todas las sesiones;
             es conservadora: nunca oculta un traslape real.
  - edificio / aula: los de la primera sesión.
  - sesiones: el detalle exacto; multihorario=True cuando las horas difieren.
Los NRC sin horario publicado (p. ej. cursos virtuales) quedan con dias=[] y
hora/edificio/aula/periodo=None.
"""
import argparse
import html
import re
import sys
from datetime import date

DIAS = ["L", "M", "I", "J", "V", "S"]  # posiciones de la columna "Días" del SIIAU


def _texto(fragmento: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragmento)).strip()


def _celdas(fragmento: str) -> list[str]:
    return [_texto(c) for c in re.findall(r"<TD[^>]*>(.*?)</TD>", fragmento, flags=re.S)]


def _fecha(dd_mm_aa: str) -> str:
    d, m, a = dd_mm_aa.strip().split("/")
    return date(2000 + int(a), int(m), int(d)).isoformat()


def _hora(hhmm_hhmm: str) -> str:
    ini, fin = hhmm_hhmm.split("-")
    return f"{ini[:2]}:{ini[2:]}-{fin[:2]}:{fin[2:]}"


def _ciclo(codigo: str) -> str:
    """202620 -> 2026B (10 = A, 20 = B)."""
    return f"{codigo[:4]}{'A' if codigo[4:] == '10' else 'B'}"


def _a_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _a_hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def parsear(ruta: str) -> list[dict]:
    s = open(ruta, encoding="utf-8").read()
    ciclo = _ciclo(re.search(r"ciclo (\d{6})", s).group(1))
    clases = []
    for bloque in re.split(r'<TR style="background-color:#[0-9A-Fa-f]+;">', s)[1:]:
        nrc, clave, materia, seccion, cr, cup, dis = _celdas(bloque.split("<TABLE", 1)[0])[:7]
        tablas = re.findall(r"<TABLE.*?</TABLE>", bloque, flags=re.S)

        sesiones = []
        for tr in re.findall(r"<TR>(.*?)</TR>", tablas[0] if tablas else "", flags=re.S):
            c = _celdas(tr)
            if len(c) < 6:
                continue
            _, hora, dias, edif, aula, periodo = c[:6]
            ini, fin = (p.strip() for p in periodo.split("-"))
            sesiones.append({
                "dias": [DIAS[i] for i, x in enumerate(dias.split()) if x != "."],
                "hora": _hora(hora),
                "edificio": edif,
                "aula": aula,
                "periodo": {"inicio": _fecha(ini), "fin": _fecha(fin)},
            })

        profesores = []
        for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", tablas[1] if len(tablas) > 1 else "", flags=re.S):
            c = _celdas(tr)
            if len(c) >= 2 and c[1] not in profesores:
                profesores.append(c[1])

        clase = {
            "ciclo": ciclo, "nrc": nrc, "clave": clave, "materia": materia,
            "seccion": seccion, "creditos": int(cr), "cupo": int(cup),
            "disponibles": int(dis),  # puede ser negativo (sobrecupo en el SIIAU)
        }
        if sesiones:
            inicios, fines = zip(*(s_["hora"].split("-") for s_ in sesiones))
            primera = sesiones[0]
            clase.update(
                dias=[d for d in DIAS if any(d in s_["dias"] for s_ in sesiones)],
                hora=f"{_a_hhmm(min(map(_a_min, inicios)))}-{_a_hhmm(max(map(_a_min, fines)))}",
                edificio=primera["edificio"], aula=primera["aula"], periodo=primera["periodo"],
            )
        else:
            clase.update(dias=[], hora=None, edificio=None, aula=None, periodo=None)
        clase.update(
            profesor=" / ".join(profesores),
            profesores=profesores,
            multihorario=len({s_["hora"] for s_ in sesiones}) > 1,
            sesiones=sesiones,
        )
        clases.append(clase)
    return clases


def _lit(valor) -> str:
    """repr compacto con comillas dobles (estilo del stub original)."""
    if isinstance(valor, str):
        return '"' + valor.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(valor, (list, tuple)):
        return "[" + ", ".join(_lit(v) for v in valor) + "]"
    if isinstance(valor, dict):
        return "{" + ", ".join(f"{_lit(k)}: {_lit(v)}" for k, v in valor.items()) + "}"
    return repr(valor)


def escribir(clases: list[dict], destino: str, origenes: list[str]) -> None:
    ciclo = clases[0]["ciclo"] if clases else "?"
    lineas = [
        '"""Oferta académica real del CUCEI (SIIAU), generada por importar_siiau.py.',
        "",
        f"Ciclo {ciclo} - {len(clases)} NRC. No editar a mano: vuelve a generar el archivo.",
        'Origen: ' + ", ".join(origenes),
        "",
        "Llaves planas (ciclo ... profesor): mismas que el CLASES_STUB original.",
        "Extras: profesores, multihorario (las sesiones tienen horas distintas; 'hora'",
        "es entonces la envolvente) y sesiones (detalle exacto por sesión).",
        '"""',
        "",
        "CLASES_STUB: list[dict] = [",
    ]
    for c in clases:
        lineas.append("    {")
        for k, v in c.items():
            if k == "sesiones":
                if not v:
                    lineas.append('        "sesiones": [],')
                    continue
                lineas.append('        "sesiones": [')
                lineas += [f"            {_lit(s_)}," for s_ in v]
                lineas.append("        ],")
            else:
                lineas.append(f"        {_lit(k)}: {_lit(v)},")
        lineas.append("    },")
    lineas.append("]")
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lineas) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("html", nargs="+", help="páginas HTML del SIIAU")
    ap.add_argument("-o", "--salida", default="clases_stub.py")
    args = ap.parse_args(argv)

    por_nrc: dict[str, dict] = {}
    for ruta in args.html:
        for c in parsear(ruta):
            por_nrc.setdefault(c["nrc"], c)
    clases = list(por_nrc.values())
    escribir(clases, args.salida, [r.replace("\\", "/").split("/")[-1] for r in args.html])
    print(f"{len(clases)} NRC -> {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
