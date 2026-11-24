import unicodedata
from itertools import combinations
from mcp.server.mcpserver import MCPServer

from clases_stub import CLASES_STUB

mcp = MCPServer("Mi servidor")

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

# Las preferencias blandas suman o restan hasta peso * ESCALA_PREFERENCIA puntos
# (el valor base de una sección ronda los 20-40 puntos).
ESCALA_PREFERENCIA = 20.0
# Distancia (en minutos) a partir de la cual "preferir_hora" ya no bonifica.
DIST_MAX_MIN = 360


# ---------------------------------------------------------------------------
# Utilidades de tiempo y texto
# ---------------------------------------------------------------------------

def _a_minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _intervalo(clase: dict) -> tuple[int, int]:
    inicio, fin = clase["hora"].split("-")
    return _a_minutos(inicio), _a_minutos(fin)


def _tiene_horario(clase: dict) -> bool:
    """False para NRC sin horario asignado (hora None y sin días, p. ej. en línea)."""
    return bool(clase.get("hora")) and bool(clase.get("dias"))


def _norm(texto: str) -> str:
    """Minúsculas y sin acentos, para comparar texto del usuario con el catálogo."""
    sin_acentos = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn").lower()


# ---------------------------------------------------------------------------
# Catálogo de restricciones (Claude solo instancia estos tipos con parámetros).
#   categoria "filtro": se aplica a cada NRC ANTES de combinar (reduce n).
#   categoria "plan":   se aplica al horario completo (poda en backtracking si
#                       es monótona: agregar clases solo puede empeorarla).
#   categoria "requisito": exige incluir una materia (no es monótona: no sirve para
#                       podar; el voraz la fija primero).
#   categoria "preferencia": solo existe como blanda.
# Dureza "dura": invalida (filtro, plan, requisito). Dureza "blanda": nunca invalida;
# suma o resta hasta peso * ESCALA_PREFERENCIA puntos al valor de cada sección.
# En las blandas, "peso" (0 < peso <= 1) es opcional y vale 0.5 por omisión.
# ---------------------------------------------------------------------------

TIPOS_RESTRICCION: dict[str, dict] = {
    "hora_max": {
        "categoria": "filtro",
        "dureza_permitida": ["dura", "blanda"],
        "descripcion": "Descarta NRC cuya clase termina después de la hora dada.",
        "campos": {"hora": "HH:MM"},
        "ejemplo": {"tipo": "hora_max", "dureza": "dura", "hora": "17:00"},
    },
    "excluir_profesor": {
        "categoria": "filtro",
        "dureza_permitida": ["dura", "blanda"],
        "descripcion": "Descarta NRC cuyo profesor contiene el texto dado (sin acentos ni mayúsculas).",
        "campos": {"profesor": "texto"},
        "ejemplo": {"tipo": "excluir_profesor", "dureza": "dura", "profesor": "Mario"},
    },
    "excluir_dias": {
        "categoria": "filtro",
        "dureza_permitida": ["dura", "blanda"],
        "descripcion": "Descarta NRC que tengan clase en alguno de esos días (L, M, I, J, V, S).",
        "campos": {"dias": "lista de códigos de día"},
        "ejemplo": {"tipo": "excluir_dias", "dureza": "dura", "dias": ["M", "J"]},
    },
    "excluir_edificio": {
        "categoria": "filtro",
        "dureza_permitida": ["dura", "blanda"],
        "descripcion": "Descarta NRC cuyo edificio coincide con el dado.",
        "campos": {"edificio": "texto"},
        "ejemplo": {"tipo": "excluir_edificio", "dureza": "dura", "edificio": "DUCT1"},
    },
    "max_horas_por_dia": {
        "categoria": "plan",
        "dureza_permitida": ["dura"],
        "descripcion": (
            "El tiempo en la universidad de cada día (de la primera hora de entrada "
            "a la última de salida) no puede superar las horas dadas."
        ),
        "campos": {"horas": "número > 0"},
        "ejemplo": {"tipo": "max_horas_por_dia", "dureza": "dura", "horas": 8},
    },
    "ventana_libre": {
        "categoria": "filtro",
        "dureza_permitida": ["dura", "blanda"],
        "descripcion": (
            "Mantiene libre una ventana horaria: descarta NRC que se traslapen con "
            "[inicio, fin) en alguno de los días dados."
        ),
        "campos": {"dias": "lista de códigos de día", "inicio": "HH:MM", "fin": "HH:MM"},
        "ejemplo": {
            "tipo": "ventana_libre", "dureza": "dura",
            "dias": ["M"], "inicio": "11:00", "fin": "13:00",
        },
    },
    "incluir_materia": {
        "categoria": "requisito",
        "dureza_permitida": ["dura", "blanda"],
        "descripcion": (
            "Dura: el horario DEBE incluir una sección de esa materia. Blanda: las "
            "secciones de esa materia suman puntos (peso 0-1), pero no es obligatoria."
        ),
        "campos": {"materia": "nombre (o parte del nombre) o clave de la materia"},
        "ejemplo": {
            "tipo": "incluir_materia", "dureza": "dura",
            "materia": "Programación para Internet",
        },
    },
    "preferir_hora": {
        "categoria": "preferencia",
        "dureza_permitida": ["blanda"],
        "descripcion": (
            "Favorece las secciones cuyo punto medio queda cerca de la hora dada "
            "(la bonificación baja linealmente hasta 0 a 6 h de distancia)."
        ),
        "campos": {"hora": "HH:MM"},
        "ejemplo": {"tipo": "preferir_hora", "dureza": "blanda", "hora": "15:00", "peso": 0.7},
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
        permitidas = TIPOS_RESTRICCION[tipo]["dureza_permitida"]
        dureza = r.get("dureza", permitidas[0])
        if dureza not in permitidas:
            raise ValueError(
                f"{tipo}: dureza {dureza!r} no permitida; usa una de {permitidas}."
            )
        faltantes = [c for c in TIPOS_RESTRICCION[tipo]["campos"] if c not in r]
        if faltantes:
            raise ValueError(f"{tipo}: faltan los campos {faltantes}.")

        n = {"tipo": tipo, "dureza": dureza}
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
        elif tipo == "ventana_libre":
            dias = [str(d).upper() for d in r["dias"]]
            invalidos = set(dias) - DIAS_VALIDOS
            if invalidos:
                raise ValueError(
                    f"ventana_libre: días inválidos {sorted(invalidos)}. Usa {sorted(DIAS_VALIDOS)}."
                )
            if _a_minutos(r["inicio"]) >= _a_minutos(r["fin"]):
                raise ValueError("ventana_libre: 'inicio' debe ser anterior a 'fin'.")
            n["dias"] = dias
            n["inicio"] = r["inicio"]
            n["fin"] = r["fin"]
        elif tipo == "incluir_materia":
            if not str(r["materia"]).strip():
                raise ValueError("incluir_materia: 'materia' no puede estar vacía.")
            n["materia"] = str(r["materia"]).strip()
        elif tipo == "preferir_hora":
            _a_minutos(r["hora"])  # lanza ValueError si el formato es inválido
            n["hora"] = r["hora"]
        if dureza == "blanda":
            peso = float(r.get("peso", 0.5))
            if not 0 < peso <= 1:
                raise ValueError(f"{tipo}: 'peso' debe estar en el rango (0, 1].")
            n["peso"] = peso
        normalizadas.append(n)
    return normalizadas


def _describir_base(r: dict) -> str:
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
    if t == "ventana_libre":
        return f"ventana libre de {r['inicio']} a {r['fin']} los días {', '.join(r['dias'])}"
    if t == "incluir_materia":
        return f"incluir la materia '{r['materia']}'"
    if t == "preferir_hora":
        return f"preferir clases cerca de las {r['hora']}"
    return t


def describir_restriccion(r: dict) -> str:
    """Eco legible de una restricción; las blandas se marcan con su peso."""
    texto = _describir_base(r)
    if r["dureza"] == "blanda":
        return f"{texto} (preferencia blanda, peso {r['peso']:g})"
    return texto


def _cumple_filtro(clase: dict, r: dict) -> bool:
    """True si el NRC se conserva bajo el filtro r."""
    t = r["tipo"]
    if t == "hora_max":
        return not _tiene_horario(clase) or _intervalo(clase)[1] <= _a_minutos(r["hora"])
    if t == "excluir_profesor":
        return _norm(r["profesor"]) not in _norm(clase["profesor"])
    if t == "excluir_dias":
        return not set(clase["dias"]) & set(r["dias"])
    if t == "excluir_edificio":
        return _norm(clase["edificio"] or "") != _norm(r["edificio"])
    if t == "ventana_libre":
        if not set(clase["dias"]) & set(r["dias"]):
            return True
        c_ini, c_fin = _intervalo(clase)
        return not (c_ini < _a_minutos(r["fin"]) and _a_minutos(r["inicio"]) < c_fin)
    raise ValueError(f"{t} no es un filtro.")


def _cumple_plan(subconjunto: list[dict], r: dict) -> bool:
    """True si el horario completo satisface la restricción de plan r."""
    if r["tipo"] == "max_horas_por_dia":
        por_dia: dict[str, tuple[int, int]] = {}
        for c in subconjunto:
            if not _tiene_horario(c):
                continue
            ini, fin = _intervalo(c)
            for d in c["dias"]:
                a, b = por_dia.get(d, (ini, fin))
                por_dia[d] = (min(a, ini), max(b, fin))
        limite = r["horas"] * 60
        return all(fin - ini <= limite for ini, fin in por_dia.values())
    raise ValueError(f"{r['tipo']} no es una restricción de plan.")


def _clase(r: dict) -> str:
    """Cómo se trata una restricción: filtro | plan | requisito | blanda."""
    if r["dureza"] == "blanda":
        return "blanda"
    return TIPOS_RESTRICCION[r["tipo"]]["categoria"]


def _coincide_materia(clase: dict, r: dict) -> bool:
    """True si la sección pertenece a la materia pedida (nombre parcial o clave)."""
    texto = _norm(r["materia"])
    return texto in _norm(clase["materia"]) or texto == _norm(clase["clave"])


def _bono_blanda(clase: dict, r: dict) -> float:
    """Puntos que una preferencia blanda suma (o resta) a una sección."""
    puntos = r["peso"] * ESCALA_PREFERENCIA
    if r["tipo"] == "preferir_hora":
        if not _tiene_horario(clase):
            return 0.0
        punto_medio = sum(_intervalo(clase)) / 2
        distancia = abs(punto_medio - _a_minutos(r["hora"]))
        return puntos * max(0.0, 1 - distancia / DIST_MAX_MIN)
    if r["tipo"] == "incluir_materia":
        return puntos if _coincide_materia(clase, r) else 0.0
    # Filtro blando: penaliza a la sección que lo incumple, sin descartarla.
    return 0.0 if _cumple_filtro(clase, r) else -puntos


def aplicar_filtros(
    candidatas: list[dict], restricciones: list[dict]
) -> tuple[list[dict], dict[str, list[str]]]:
    """Aplica los filtros y devuelve (candidatas restantes, diagnóstico).

    El diagnóstico dice cuántos/cuáles NRC elimina CADA filtro por sí solo,
    para que Claude sepa qué restricción relajar si no hay solución.
    """
    filtros = [r for r in restricciones if _clase(r) == "filtro"]
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


def _valor(clase: dict, blandas: list[dict] | None = None) -> float:
    """Valor base + bonificaciones y penalizaciones de las preferencias blandas."""
    return valor_clase(clase) + sum(_bono_blanda(clase, r) for r in blandas or [])


def _es_factible(
    subconjunto: list[dict],
    max_creditos: int,
    plan: list[dict],
    requisitos: list[dict] | None = None,
) -> bool:
    if sum(c["creditos"] for c in subconjunto) > max_creditos:
        return False
    for a, b in combinations(subconjunto, 2):
        if hay_conflicto(a, b):
            return False
    if not all(_cumple_plan(subconjunto, r) for r in plan):
        return False
    return all(
        any(_coincide_materia(c, r) for c in subconjunto) for r in requisitos or []
    )


def _resultado(
    estrategia: str,
    elegidas: list[dict],
    evaluaciones: int,
    blandas: list[dict] | None = None,
) -> dict:
    base = sum(valor_clase(c) for c in elegidas)
    total = sum(_valor(c, blandas) for c in elegidas)
    return {
        "estrategia": estrategia,
        "nrcs": [c["nrc"] for c in elegidas],
        "materias": [c["materia"] for c in elegidas],
        "valor_total": round(total, 2),
        "valor_base": round(base, 2),
        "valor_preferencias": round(total - base, 2),
        "creditos_total": sum(c["creditos"] for c in elegidas),
        "evaluaciones": evaluaciones,
    }


# ---------------------------------------------------------------------------
# Estrategia 1: fuerza bruta, O(2^n * n^2). Óptima; sirve como oráculo.
# ---------------------------------------------------------------------------

def horario_fuerza_bruta(
    candidatas: list[dict],
    max_creditos: int,
    plan: list[dict] | None = None,
    requisitos: list[dict] | None = None,
    blandas: list[dict] | None = None,
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
        if not _es_factible(subconjunto, max_creditos, plan, requisitos):
            continue
        valor = sum(_valor(c, blandas) for c in subconjunto)
        if valor > mejor_valor:
            mejor_valor = valor
            mejor = subconjunto
    return _resultado("fuerza_bruta", mejor, evaluaciones, blandas)


# ---------------------------------------------------------------------------
# Estrategia 2: voraz por valor/crédito, O(n log n) + chequeo de conflictos.
# Muy rápida, pero no garantiza el óptimo.
# ---------------------------------------------------------------------------

def _puede_agregar(
    clase: dict, elegidas: list[dict], creditos: int, max_creditos: int, plan: list[dict]
) -> bool:
    if creditos + clase["creditos"] > max_creditos:
        return False
    if any(hay_conflicto(clase, otra) for otra in elegidas):
        return False
    # Las restricciones de plan son monótonas: si agregar la clase las rompe,
    # ningún horario posterior que la incluya puede cumplirlas.
    return all(_cumple_plan(elegidas + [clase], r) for r in plan)


def horario_voraz(
    candidatas: list[dict],
    max_creditos: int,
    plan: list[dict] | None = None,
    requisitos: list[dict] | None = None,
    blandas: list[dict] | None = None,
) -> dict:
    plan = plan or []
    requisitos = requisitos or []
    elegidas: list[dict] = []
    creditos = 0
    evaluaciones = 0

    # 1) Materias obligatorias: la mejor sección compatible de cada una.
    #    Limitación de la heurística: no reconsidera esta elección después.
    for r in requisitos:
        if any(_coincide_materia(c, r) for c in elegidas):
            continue
        opciones = sorted(
            (c for c in candidatas if _coincide_materia(c, r)),
            key=lambda c: (-_valor(c, blandas), c["nrc"]),
        )
        for clase in opciones:
            evaluaciones += 1
            if _puede_agregar(clase, elegidas, creditos, max_creditos, plan):
                elegidas.append(clase)
                creditos += clase["creditos"]
                break
        else:
            # Ninguna sección cabe: el voraz no puede cumplir el requisito.
            return _resultado("voraz", [], evaluaciones, blandas)

    # 2) El resto, por valor/crédito.
    ordenadas = sorted(
        candidatas,
        key=lambda c: (-_valor(c, blandas) / max(c["creditos"], 1), c["nrc"]),
    )
    for clase in ordenadas:
        if clase in elegidas:
            continue
        evaluaciones += 1
        if _valor(clase, blandas) <= 0:
            continue
        if not _puede_agregar(clase, elegidas, creditos, max_creditos, plan):
            continue
        elegidas.append(clase)
        creditos += clase["creditos"]
    return _resultado("voraz", elegidas, evaluaciones, blandas)


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
    requisitos = [r for r in reglas if _clase(r) == "requisito"]
    blandas = [r for r in reglas if _clase(r) == "blanda"]
    antes = {
        describir_restriccion(r): sum(_coincide_materia(c, r) for c in candidatas)
        for r in requisitos
    }

    candidatas, diagnostico = aplicar_filtros(candidatas, reglas)
    plan = [r for r in reglas if _clase(r) == "plan"]

    resultado = ESTRATEGIAS[estrategia](candidatas, max_creditos, plan, requisitos, blandas)
    resultado["restricciones_aplicadas"] = [describir_restriccion(r) for r in reglas]
    resultado["candidatas_iniciales"] = n_inicial
    resultado["candidatas_tras_filtros"] = len(candidatas)
    resultado["descartados_por_filtro"] = diagnostico
    resultado["requisitos"] = {
        describir_restriccion(r): {
            "secciones_antes_de_filtros": antes[describir_restriccion(r)],
            "secciones_tras_filtros": sum(_coincide_materia(c, r) for c in candidatas),
        }
        for r in requisitos
    }
    if not resultado["nrcs"]:
        resultado["sin_solucion"] = True
        resultado["mensaje"] = (
            "No se encontró ningún horario. Revisa 'descartados_por_filtro' para ver "
            "qué restricción eliminó más NRC y considera relajarla. Si hay requisitos "
            "('incluir_materia' dura), revisa 'requisitos': puede que ninguna sección "
            "haya sobrevivido a los filtros o que no quepa con el resto del horario."
        )
    return resultado


@mcp.tool()
def obtener_clases_disponibles() -> list[dict]:
    """Retorna todas las clases disponibles (oferta real del CUCEI, ciclo 2026B, de clases_stub.py)."""
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
    Con dureza "blanda" una restricción nunca descarta nada: solo suma o resta puntos
    según 'peso' (0 a 1, por omisión 0.5). 'incluir_materia' con dureza "dura" obliga a
    que el horario tenga esa materia ('requisitos' indica cuántas secciones sobreviven).
    """
    return resolver(estrategia, max_creditos, nrcs, restricciones)

if __name__ == "__main__":
    mcp.run()
