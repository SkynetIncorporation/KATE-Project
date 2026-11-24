import unicodedata
from itertools import combinations
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("Mi servidor")

# Datos de ejemplo (stub) de la oferta académica del CUCEI.
# Campos basados en el SIIAU: ciclo, NRC, clave, materia, sección, créditos,
# cupo, disponibles, días, hora, edificio, aula, periodo y profesor.
CLASES_STUB: list[dict] = [
    {
        "ciclo": "2026B",
        "nrc": "120345",
        "clave": "IL350",
        "materia": "Programación Orientada a Objetos",
        "seccion": "D01",
        "creditos": 8,
        "cupo": 40,
        "disponibles": 12,
        "dias": ["L", "M", "V"],
        "hora": "07:00-08:55",
        "edificio": "DBETA",
        "aula": "A102",
        "periodo": {"inicio": "2026-08-31", "fin": "2026-12-11"},
        "profesor": "Dr. Alejandro Ramírez Torres",
    },
    {
        "ciclo": "2026B",
        "nrc": "120378",
        "clave": "IL355",
        "materia": "Estructuras de Datos",
        "seccion": "D02",
        "creditos": 8,
        "cupo": 35,
        "disponibles": 0,
        "dias": ["M", "J"],
        "hora": "09:00-10:55",
        "edificio": "DUCT1",
        "aula": "B204",
        "periodo": {"inicio": "2026-08-31", "fin": "2026-12-11"},
        "profesor": "Mtra. Laura Gómez Hernández",
    },
    {
        "ciclo": "2026B",
        "nrc": "121002",
        "clave": "IL410",
        "materia": "Bases de Datos",
        "seccion": "D03",
        "creditos": 8,
        "cupo": 30,
        "disponibles": 7,
        "dias": ["L", "J"],
        "hora": "11:00-12:55",
        "edificio": "DBETA",
        "aula": "LAB3",
        "periodo": {"inicio": "2026-08-31", "fin": "2026-12-11"},
        "profesor": "Dr. Carlos Medina Ortega",
    },
    {
        "ciclo": "2026B",
        "nrc": "121540",
        "clave": "MA201",
        "materia": "Cálculo Diferencial e Integral",
        "seccion": "D05",
        "creditos": 10,
        "cupo": 45,
        "disponibles": 21,
        "dias": ["L", "M", "J", "V"],
        "hora": "13:00-14:55",
        "edificio": "DUCT2",
        "aula": "C305",
        "periodo": {"inicio": "2026-08-31", "fin": "2026-12-11"},
        "profesor": "Mtro. Ricardo Salazar Núñez",
    },
    {
        "ciclo": "2026B",
        "nrc": "122210",
        "clave": "FI110",
        "materia": "Física General",
        "seccion": "D04",
        "creditos": 8,
        "cupo": 50,
        "disponibles": 3,
        "dias": ["M", "V"],
        "hora": "15:00-16:55",
        "edificio": "DALFA",
        "aula": "D101",
        "periodo": {"inicio": "2026-08-31", "fin": "2026-12-11"},
        "profesor": "Dra. Patricia Vázquez Luna",
    },
]

# Calificación (estrellas 1-5) de cada profesor, tipo SIIAPP (stub inventado).
ESTRELLAS_STUB: dict[str, float] = {
    "Dr. Alejandro Ramírez Torres": 4.5,
    "Mtra. Laura Gómez Hernández": 3.8,
    "Dr. Carlos Medina Ortega": 2.9,
    "Mtro. Ricardo Salazar Núñez": 4.2,
    "Dra. Patricia Vázquez Luna": 3.5,
}
ESTRELLAS_DEFAULT = 3.0

# Máximo de combinaciones que la fuerza bruta acepta (2^n crece muy rápido).
MAX_N_FUERZA_BRUTA = 25

# Códigos de día usados en el catálogo (M = martes, I = miércoles).
DIAS_VALIDOS = {"L", "M", "I", "J", "V", "S"}


# ---------------------------------------------------------------------------
# Utilidades de tiempo y texto
# ---------------------------------------------------------------------------

def _a_minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _intervalo(clase: dict) -> tuple[int, int]:
    inicio, fin = clase["hora"].split("-")
    return _a_minutos(inicio), _a_minutos(fin)


def _norm(texto: str) -> str:
    """Minúsculas y sin acentos, para comparar texto del usuario con el catálogo."""
    sin_acentos = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn").lower()


# ---------------------------------------------------------------------------
# Catálogo de restricciones (Claude solo instancia estos tipos con parámetros).
#   categoria "filtro": se aplica a cada NRC ANTES de combinar (reduce n).
#   categoria "plan":   se aplica al horario completo (poda en backtracking si
#                       es monótona: agregar clases solo puede empeorarla).
# Por ahora solo existe la dureza "dura"; las preferencias (blandas) vendrán después.
# ---------------------------------------------------------------------------

TIPOS_RESTRICCION: dict[str, dict] = {
    "hora_max": {
        "categoria": "filtro",
        "descripcion": "Descarta NRC cuya clase termina después de la hora dada.",
        "campos": {"hora": "HH:MM"},
        "ejemplo": {"tipo": "hora_max", "dureza": "dura", "hora": "17:00"},
    },
    "excluir_profesor": {
        "categoria": "filtro",
        "descripcion": "Descarta NRC cuyo profesor contiene el texto dado (sin acentos ni mayúsculas).",
        "campos": {"profesor": "texto"},
        "ejemplo": {"tipo": "excluir_profesor", "dureza": "dura", "profesor": "Mario"},
    },
    "excluir_dias": {
        "categoria": "filtro",
        "descripcion": "Descarta NRC que tengan clase en alguno de esos días (L, M, I, J, V, S).",
        "campos": {"dias": "lista de códigos de día"},
        "ejemplo": {"tipo": "excluir_dias", "dureza": "dura", "dias": ["M", "J"]},
    },
    "excluir_edificio": {
        "categoria": "filtro",
        "descripcion": "Descarta NRC cuyo edificio coincide con el dado.",
        "campos": {"edificio": "texto"},
        "ejemplo": {"tipo": "excluir_edificio", "dureza": "dura", "edificio": "DUCT1"},
    },
    "max_horas_por_dia": {
        "categoria": "plan",
        "descripcion": (
            "El tiempo en la universidad de cada día (de la primera hora de entrada "
            "a la última de salida) no puede superar las horas dadas."
        ),
        "campos": {"horas": "número > 0"},
        "ejemplo": {"tipo": "max_horas_por_dia", "dureza": "dura", "horas": 8},
    },
}


def validar_restricciones(restricciones: list[dict] | None) -> list[dict]:
    """Valida contra el catálogo y devuelve las restricciones normalizadas."""
    normalizadas: list[dict] = []
    for r in restricciones or []:
        tipo = r.get("tipo")
        if tipo not in TIPOS_RESTRICCION:
            raise ValueError(
                f"Tipo de restricción desconocido: {tipo!r}. "
                f"Disponibles: {list(TIPOS_RESTRICCION)}."
            )
        dureza = r.get("dureza", "dura")
        if dureza != "dura":
            raise ValueError(
                f"{tipo}: por ahora solo se soporta dureza 'dura' (recibió {dureza!r})."
            )
        faltantes = [c for c in TIPOS_RESTRICCION[tipo]["campos"] if c not in r]
        if faltantes:
            raise ValueError(f"{tipo}: faltan los campos {faltantes}.")

        n = {"tipo": tipo, "dureza": "dura"}
        if tipo == "hora_max":
            _a_minutos(r["hora"])  # lanza ValueError si el formato es inválido
            n["hora"] = r["hora"]
        elif tipo == "excluir_profesor":
            n["profesor"] = str(r["profesor"])
        elif tipo == "excluir_dias":
            dias = [str(d).upper() for d in r["dias"]]
            invalidos = set(dias) - DIAS_VALIDOS
            if invalidos:
                raise ValueError(
                    f"excluir_dias: días inválidos {sorted(invalidos)}. Usa {sorted(DIAS_VALIDOS)}."
                )
            n["dias"] = dias
        elif tipo == "excluir_edificio":
            n["edificio"] = str(r["edificio"])
        elif tipo == "max_horas_por_dia":
            if float(r["horas"]) <= 0:
                raise ValueError("max_horas_por_dia: 'horas' debe ser mayor que 0.")
            n["horas"] = float(r["horas"])
        normalizadas.append(n)
    return normalizadas


def describir_restriccion(r: dict) -> str:
    """Eco legible de una restricción, para que Claude/usuario verifiquen la interpretación."""
    t = r["tipo"]
    if t == "hora_max":
        return f"sin clases que terminen después de las {r['hora']}"
    if t == "excluir_profesor":
        return f"sin profesores que coincidan con '{r['profesor']}'"
    if t == "excluir_dias":
        return f"sin clases los días {', '.join(r['dias'])}"
    if t == "excluir_edificio":
        return f"sin clases en el edificio {r['edificio']}"
    if t == "max_horas_por_dia":
        return f"máximo {r['horas']:g} h por día en la universidad"
    return t


def _cumple_filtro(clase: dict, r: dict) -> bool:
    """True si el NRC se conserva bajo el filtro r."""
    t = r["tipo"]
    if t == "hora_max":
        return _intervalo(clase)[1] <= _a_minutos(r["hora"])
    if t == "excluir_profesor":
        return _norm(r["profesor"]) not in _norm(clase["profesor"])
    if t == "excluir_dias":
        return not set(clase["dias"]) & set(r["dias"])
    if t == "excluir_edificio":
        return _norm(clase["edificio"]) != _norm(r["edificio"])
    raise ValueError(f"{t} no es un filtro.")


def _cumple_plan(subconjunto: list[dict], r: dict) -> bool:
    """True si el horario completo satisface la restricción de plan r."""
    if r["tipo"] == "max_horas_por_dia":
        por_dia: dict[str, tuple[int, int]] = {}
        for c in subconjunto:
            ini, fin = _intervalo(c)
            for d in c["dias"]:
                a, b = por_dia.get(d, (ini, fin))
                por_dia[d] = (min(a, ini), max(b, fin))
        limite = r["horas"] * 60
        return all(fin - ini <= limite for ini, fin in por_dia.values())
    raise ValueError(f"{r['tipo']} no es una restricción de plan.")


def aplicar_filtros(
    candidatas: list[dict], restricciones: list[dict]
) -> tuple[list[dict], dict[str, list[str]]]:
    """Aplica los filtros y devuelve (candidatas restantes, diagnóstico).

    El diagnóstico dice cuántos/cuáles NRC elimina CADA filtro por sí solo,
    para que Claude sepa qué restricción relajar si no hay solución.
    """
    filtros = [r for r in restricciones if TIPOS_RESTRICCION[r["tipo"]]["categoria"] == "filtro"]
    diagnostico = {
        describir_restriccion(f): [c["nrc"] for c in candidatas if not _cumple_filtro(c, f)]
        for f in filtros
    }
    restantes = [c for c in candidatas if all(_cumple_filtro(c, f) for f in filtros)]
    return restantes, diagnostico


# ---------------------------------------------------------------------------
# Modelo del problema: selección de secciones (NRC) sin conflictos.
#   - Cada candidata tiene un valor y un costo en créditos.
#   - Dos NRC no pueden coexistir si se traslapan en día y hora,
#     o si son la misma materia (misma clave, distinta sección).
#   - La suma de créditos no puede pasar de max_creditos.
#   - El horario debe cumplir las restricciones de plan.
# Generaliza la mochila 0/1 (capacidad = créditos) con conflictos entre pares.
# ---------------------------------------------------------------------------

def hay_conflicto(a: dict, b: dict) -> bool:
    """True si a y b no pueden estar en el mismo horario."""
    if a["clave"] == b["clave"]:
        return True
    if not set(a["dias"]) & set(b["dias"]):
        return False
    a_ini, a_fin = _intervalo(a)
    b_ini, b_fin = _intervalo(b)
    return a_ini < b_fin and b_ini < a_fin


def valor_clase(clase: dict) -> float:
    """Función de valor ARBITRARIA (ajustable) de una sección.

    valor = 2 * créditos + 4 * estrellas del profesor
            + 3 si hay lugares disponibles, -50 si el grupo está lleno.
    """
    estrellas = ESTRELLAS_STUB.get(clase["profesor"], ESTRELLAS_DEFAULT)
    valor = 2 * clase["creditos"] + 4 * estrellas
    valor += 3 if clase["disponibles"] > 0 else -50
    return valor


def _es_factible(subconjunto: list[dict], max_creditos: int, plan: list[dict]) -> bool:
    if sum(c["creditos"] for c in subconjunto) > max_creditos:
        return False
    for a, b in combinations(subconjunto, 2):
        if hay_conflicto(a, b):
            return False
    return all(_cumple_plan(subconjunto, r) for r in plan)


def _resultado(estrategia: str, elegidas: list[dict], evaluaciones: int) -> dict:
    return {
        "estrategia": estrategia,
        "nrcs": [c["nrc"] for c in elegidas],
        "materias": [c["materia"] for c in elegidas],
        "valor_total": round(sum(valor_clase(c) for c in elegidas), 2),
        "creditos_total": sum(c["creditos"] for c in elegidas),
        "evaluaciones": evaluaciones,
    }


# ---------------------------------------------------------------------------
# Estrategia 1: fuerza bruta, O(2^n * n^2). Óptima; sirve como oráculo.
# ---------------------------------------------------------------------------

def horario_fuerza_bruta(
    candidatas: list[dict], max_creditos: int, plan: list[dict] | None = None
) -> dict:
    plan = plan or []
    n = len(candidatas)
    if n > MAX_N_FUERZA_BRUTA:
        raise ValueError(
            f"Fuerza bruta limitada a n <= {MAX_N_FUERZA_BRUTA} (recibió {n})."
        )
    mejor: list[dict] = []
    mejor_valor = float("-inf")
    evaluaciones = 0
    for mascara in range(1 << n):
        subconjunto = [candidatas[i] for i in range(n) if mascara >> i & 1]
        evaluaciones += 1
        if not _es_factible(subconjunto, max_creditos, plan):
            continue
        valor = sum(valor_clase(c) for c in subconjunto)
        if valor > mejor_valor:
            mejor_valor = valor
            mejor = subconjunto
    return _resultado("fuerza_bruta", mejor, evaluaciones)


# ---------------------------------------------------------------------------
# Estrategia 2: voraz por valor/crédito, O(n log n) + chequeo de conflictos.
# Muy rápida, pero no garantiza el óptimo.
# ---------------------------------------------------------------------------

def horario_voraz(
    candidatas: list[dict], max_creditos: int, plan: list[dict] | None = None
) -> dict:
    plan = plan or []
    ordenadas = sorted(
        candidatas,
        key=lambda c: (-valor_clase(c) / c["creditos"], c["nrc"]),
    )
    elegidas: list[dict] = []
    creditos = 0
    evaluaciones = 0
    for clase in ordenadas:
        evaluaciones += 1
        if valor_clase(clase) <= 0:
            continue
        if creditos + clase["creditos"] > max_creditos:
            continue
        if any(hay_conflicto(clase, otra) for otra in elegidas):
            continue
        # Las restricciones de plan son monótonas: si agregar la clase las rompe,
        # ningún horario posterior que la incluya puede cumplirlas.
        if not all(_cumple_plan(elegidas + [clase], r) for r in plan):
            continue
        elegidas.append(clase)
        creditos += clase["creditos"]
    return _resultado("voraz", elegidas, evaluaciones)


ESTRATEGIAS = {
    "fuerza_bruta": horario_fuerza_bruta,
    "voraz": horario_voraz,
}


def resolver(
    estrategia: str,
    max_creditos: int,
    nrcs: list[str] | None = None,
    restricciones: list[dict] | None = None,
) -> dict:
    """Pipeline completo: validar -> filtrar NRC -> algoritmo con restricciones de plan."""
    if estrategia not in ESTRATEGIAS:
        raise ValueError(f"Estrategia desconocida: {estrategia}. Usa {list(ESTRATEGIAS)}.")
    reglas = validar_restricciones(restricciones)
    candidatas = [c for c in CLASES_STUB if nrcs is None or c["nrc"] in nrcs]
    n_inicial = len(candidatas)

    candidatas, diagnostico = aplicar_filtros(candidatas, reglas)
    plan = [r for r in reglas if TIPOS_RESTRICCION[r["tipo"]]["categoria"] == "plan"]

    resultado = ESTRATEGIAS[estrategia](candidatas, max_creditos, plan)
    resultado["restricciones_aplicadas"] = [describir_restriccion(r) for r in reglas]
    resultado["candidatas_iniciales"] = n_inicial
    resultado["candidatas_tras_filtros"] = len(candidatas)
    resultado["descartados_por_filtro"] = diagnostico
    if not resultado["nrcs"]:
        resultado["sin_solucion"] = True
        resultado["mensaje"] = (
            "No se encontró ningún horario. Revisa 'descartados_por_filtro' para ver "
            "qué restricción eliminó más NRC y considera relajarla."
        )
    return resultado


@mcp.tool()
def obtener_clases_disponibles() -> list[dict]:
    """Retorna todas las clases disponibles (stub con datos inventados del CUCEI)."""
    return CLASES_STUB


@mcp.tool()
def listar_tipos_restriccion() -> dict:
    """Catálogo de tipos de restricción que acepta armar_horario, con campos y ejemplos.

    Consúltalo antes de traducir las peticiones del usuario a restricciones.
    """
    return TIPOS_RESTRICCION


@mcp.tool()
def armar_horario(
    estrategia: str = "voraz",
    max_creditos: int = 30,
    nrcs: list[str] | None = None,
    restricciones: list[dict] | None = None,
) -> dict:
    """Arma un horario sin conflictos maximizando el valor total.

    estrategia: "fuerza_bruta" (óptima, lenta) o "voraz" (rápida, aproximada).
    max_creditos: tope de créditos del horario.
    nrcs: NRC candidatos (si se omite, usa todas las clases del catálogo).
    restricciones: lista de restricciones del catálogo (ver listar_tipos_restriccion),
        por ejemplo {"tipo": "excluir_dias", "dureza": "dura", "dias": ["M", "J"]}.
    La respuesta incluye 'restricciones_aplicadas' (eco de lo interpretado) y
    'descartados_por_filtro' (qué NRC eliminó cada filtro) para ajustar si no hay solución.
    """
    return resolver(estrategia, max_creditos, nrcs, restricciones)

if __name__ == "__main__":
    mcp.run()
