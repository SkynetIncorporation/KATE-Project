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

# Niveles de importancia que Claude asigna según el tono del usuario. Cada nivel
# es un multiplicador del peso (puntos = peso * ESCALA_PREFERENCIA). Son discretos
# a propósito: así las corridas son reproducibles y comparables.
# "casi_obligatoria" vale 50 * 20 = 1000 puntos: supera cualquier ganancia posible
# de una sección, así que solo se viola si una restricción DURA lo obliga.
IMPORTANCIAS: dict[str, float] = {
    "ligera": 0.25,
    "normal": 0.5,
    "fuerte": 1.0,
    "casi_obligatoria": 50.0,
}
# Una preferencia parcial (preferir_hora) se reporta como violación si cumple
# menos de esta fracción de su bonificación máxima.
UMBRAL_CUMPLIMIENTO = 0.5


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
#   categoria "minimo":   cota inferior sobre el horario completo (agregar clases solo
#                       puede ayudar, así que tampoco sirve para podar; el voraz la
#                       comprueba al final y, si falta, intenta completar).
#   categoria "preferencia": solo existe como blanda.
# Dureza "dura": invalida (filtro, plan, requisito). Dureza "blanda": nunca invalida;
# suma o resta hasta peso * ESCALA_PREFERENCIA puntos al valor de cada sección.
# En las blandas, "importancia" (ligera | normal | fuerte | casi_obligatoria) fija el
# peso desde el tono del usuario. Alternativa: "peso" numérico (0 < peso <= 1);
# no se pueden dar ambos. Sin ninguno, el peso vale 0.5 (= "normal").
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
    "max_creditos": {
        "categoria": "plan",
        "dureza_permitida": ["dura"],
        "descripcion": "La suma de créditos del horario no puede superar los créditos dados.",
        "campos": {"creditos": "número > 0"},
        "ejemplo": {"tipo": "max_creditos", "dureza": "dura", "creditos": 30},
    },
    "min_creditos": {
        "categoria": "minimo",
        "dureza_permitida": ["dura"],
        "descripcion": "La suma de créditos del horario debe ser al menos los créditos dados.",
        "campos": {"creditos": "número > 0"},
        "ejemplo": {"tipo": "min_creditos", "dureza": "dura", "creditos": 20},
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
        "ejemplo": {
            "tipo": "preferir_hora", "dureza": "blanda", "hora": "15:00",
            "importancia": "fuerte",
        },
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
        elif tipo in ("max_creditos", "min_creditos"):
            if float(r["creditos"]) <= 0:
                raise ValueError(f"{tipo}: 'creditos' debe ser mayor que 0.")
            n["creditos"] = float(r["creditos"])
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
            if "importancia" in r and "peso" in r:
                raise ValueError(f"{tipo}: usa 'importancia' o 'peso', no ambos.")
            if "importancia" in r:
                importancia = str(r["importancia"]).lower()
                if importancia not in IMPORTANCIAS:
                    raise ValueError(
                        f"{tipo}: importancia {r['importancia']!r} desconocida. "
                        f"Usa una de {list(IMPORTANCIAS)}."
                    )
                n["importancia"] = importancia
                n["peso"] = IMPORTANCIAS[importancia]
            else:
                peso = float(r.get("peso", 0.5))
                if not 0 < peso <= 1:
                    raise ValueError(f"{tipo}: 'peso' debe estar en el rango (0, 1].")
                n["peso"] = peso
        elif "importancia" in r:
            raise ValueError(
                f"{tipo}: 'importancia' solo aplica a restricciones blandas; "
                "una restricción dura no tiene niveles."
            )
        normalizadas.append(n)
    maximos = [float(n["creditos"]) for n in normalizadas if n["tipo"] == "max_creditos"]
    minimos = [float(n["creditos"]) for n in normalizadas if n["tipo"] == "min_creditos"]
    if maximos and minimos and max(minimos) > min(maximos):
        raise ValueError(
            f"min_creditos ({max(minimos):g}) no puede ser mayor que "
            f"max_creditos ({min(maximos):g})."
        )
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
    if t == "max_creditos":
        return f"máximo {r['creditos']:g} créditos en total"
    if t == "min_creditos":
        return f"mínimo {r['creditos']:g} créditos en total"
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
        nivel = r.get("importancia")
        etiqueta = f"importancia {nivel}" if nivel else f"peso {r['peso']:g}"
        return f"{texto} (preferencia blanda, {etiqueta})"
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


def _total_creditos(subconjunto: list[dict]) -> int:
    return sum(c["creditos"] for c in subconjunto)


def _cumple_plan(subconjunto: list[dict], r: dict) -> bool:
    """True si el horario (posiblemente parcial) satisface la restricción de plan r."""
    if r["tipo"] == "max_creditos":
        return _total_creditos(subconjunto) <= r["creditos"]
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


def _cumple_minimo(subconjunto: list[dict], r: dict) -> bool:
    """True si el horario COMPLETO satisface la cota mínima r (no aplica a parciales)."""
    if r["tipo"] == "min_creditos":
        return _total_creditos(subconjunto) >= r["creditos"]
    raise ValueError(f"{r['tipo']} no es una restricción de mínimo.")


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


def _violaciones(elegidas: list[dict], blandas: list[dict] | None) -> list[dict]:
    """Preferencias blandas que el horario incumple (total o parcialmente).

    Cada entrada dice qué restricción, en qué NRC y cuántos puntos costó; es lo que
    Claude necesita para explicar los tradeoffs de un plan.
    """
    resultado: list[dict] = []
    for r in blandas or []:
        puntos = r["peso"] * ESCALA_PREFERENCIA
        texto = describir_restriccion(r)
        if r["tipo"] == "incluir_materia":
            if not any(_coincide_materia(c, r) for c in elegidas):
                resultado.append({
                    "restriccion": texto, "nrc": None, "materia": r["materia"],
                    "costo": round(puntos, 2),
                })
        elif r["tipo"] == "preferir_hora":
            for c in elegidas:
                bono = _bono_blanda(c, r)
                if bono < UMBRAL_CUMPLIMIENTO * puntos:
                    resultado.append({
                        "restriccion": texto, "nrc": c["nrc"], "materia": c["materia"],
                        "costo": round(puntos - bono, 2),
                    })
        else:
            for c in elegidas:
                if not _cumple_filtro(c, r):
                    resultado.append({
                        "restriccion": texto, "nrc": c["nrc"], "materia": c["materia"],
                        "costo": round(puntos, 2),
                    })
    return resultado


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
#   - El horario debe cumplir las restricciones de plan (incluido el tope de
#     créditos, 'max_creditos') y las cotas mínimas ('min_creditos').
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
    plan: list[dict],
    requisitos: list[dict] | None = None,
    minimos: list[dict] | None = None,
) -> bool:
    if not all(_cumple_plan(subconjunto, r) for r in plan):
        return False
    for a, b in combinations(subconjunto, 2):
        if hay_conflicto(a, b):
            return False
    if not all(_cumple_minimo(subconjunto, r) for r in minimos or []):
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
    violaciones = _violaciones(elegidas, blandas)
    return {
        "estrategia": estrategia,
        "nrcs": [c["nrc"] for c in elegidas],
        "materias": [c["materia"] for c in elegidas],
        "valor_total": round(total, 2),
        "valor_base": round(base, 2),
        "valor_preferencias": round(total - base, 2),
        "creditos_total": sum(c["creditos"] for c in elegidas),
        "evaluaciones": evaluaciones,
        "violaciones": violaciones,
        "costo_violaciones": round(sum(v["costo"] for v in violaciones), 2),
    }


# ---------------------------------------------------------------------------
# Estrategia 1: fuerza bruta, O(2^n * n^2). Óptima; sirve como oráculo.
# ---------------------------------------------------------------------------

def horario_fuerza_bruta(
    candidatas: list[dict],
    plan: list[dict] | None = None,
    requisitos: list[dict] | None = None,
    blandas: list[dict] | None = None,
    minimos: list[dict] | None = None,
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
        if not _es_factible(subconjunto, plan, requisitos, minimos):
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

def _puede_agregar(clase: dict, elegidas: list[dict], plan: list[dict]) -> bool:
    if any(hay_conflicto(clase, otra) for otra in elegidas):
        return False
    # Las restricciones de plan son monótonas: si agregar la clase las rompe,
    # ningún horario posterior que la incluya puede cumplirlas.
    return all(_cumple_plan(elegidas + [clase], r) for r in plan)


def horario_voraz(
    candidatas: list[dict],
    plan: list[dict] | None = None,
    requisitos: list[dict] | None = None,
    blandas: list[dict] | None = None,
    minimos: list[dict] | None = None,
) -> dict:
    plan = plan or []
    requisitos = requisitos or []
    minimos = minimos or []
    elegidas: list[dict] = []
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
            if _puede_agregar(clase, elegidas, plan):
                elegidas.append(clase)
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
        if not _puede_agregar(clase, elegidas, plan):
            continue
        elegidas.append(clase)

    # 3) Cotas mínimas (p. ej. min_creditos): si el horario se quedó corto, se
    #    completa con las secciones restantes que quepan, aunque su valor sea <= 0
    #    (una restricción dura pesa más que el valor). Si aun así no se alcanza,
    #    el voraz no puede cumplirla (limitación de la heurística).
    if not all(_cumple_minimo(elegidas, r) for r in minimos):
        for clase in ordenadas:
            if clase in elegidas:
                continue
            evaluaciones += 1
            if _puede_agregar(clase, elegidas, plan):
                elegidas.append(clase)
                if all(_cumple_minimo(elegidas, r) for r in minimos):
                    break
        if not all(_cumple_minimo(elegidas, r) for r in minimos):
            return _resultado("voraz", [], evaluaciones, blandas)
    return _resultado("voraz", elegidas, evaluaciones, blandas)


# ---------------------------------------------------------------------------
# Estrategia 3: backtracking con poda (branch & bound). Óptima.
#
# Cada nodo del árbol es un horario parcial; sus hijos agregan una sección más
# (en orden fijo, sin repetir subconjuntos). Dos tipos de poda:
#   - Factibilidad (siempre): solo se extienden ramas donde la sección nueva no
#     choca con las ya elegidas ni rompe una restricción de plan (monótonas), y
#     se corta si un requisito o un mínimo de créditos ya es inalcanzable.
#   - Cota (poda_cota=True): se corta si el valor actual más el máximo que aún
#     se podría sumar (a lo más una sección por materia, solo valores > 0) no
#     supera al mejor horario encontrado. La cota es admisible, así que nunca
#     descarta el óptimo.
# Peor caso O(2^n), pero en la práctica explora una fracción de los nodos.
# ---------------------------------------------------------------------------

# Tope de nodos para que una instancia enorme no cuelgue la herramienta MCP.
# Si se alcanza, se devuelve el mejor horario hallado con optimo_garantizado=False.
MAX_NODOS_BACKTRACKING = 500_000


class _LimiteNodos(Exception):
    """Se alcanzó MAX_NODOS_BACKTRACKING."""


def horario_backtracking(
    candidatas: list[dict],
    plan: list[dict] | None = None,
    requisitos: list[dict] | None = None,
    blandas: list[dict] | None = None,
    minimos: list[dict] | None = None,
    poda_cota: bool = True,
) -> dict:
    plan = plan or []
    requisitos = requisitos or []
    minimos = minimos or []
    nombre = "backtracking" if poda_cota else "backtracking_sin_cota"

    # Orden por valor/crédito: la primera ruta en profundidad imita al voraz y da
    # una buena cota inferior desde el inicio.
    ordenadas = sorted(
        candidatas,
        key=lambda c: (-_valor(c, blandas) / max(c["creditos"], 1), c["nrc"]),
    )
    valores = [_valor(c, blandas) for c in ordenadas]
    # Con requisitos o mínimos, una sección de valor <= 0 puede ser necesaria.
    exigen_negativas = bool(requisitos or minimos)
    est = {
        "nodos": 0,
        "podas_factibilidad": 0,
        "podas_cota": 0,
        "mejor": [],
        "mejor_valor": float("-inf"),
    }

    def cumple_completo(elegidas: list[dict]) -> bool:
        return all(
            any(_coincide_materia(c, r) for c in elegidas) for r in requisitos
        ) and all(_cumple_minimo(elegidas, r) for r in minimos)

    def alcanzable(elegidas: list[dict], creditos: int, viables: list[int]) -> bool:
        """False si ningún descendiente puede cumplir los requisitos o mínimos."""
        for r in requisitos:
            if not any(_coincide_materia(c, r) for c in elegidas) and not any(
                _coincide_materia(ordenadas[j], r) for j in viables
            ):
                return False
        if minimos:
            por_clave: dict[str, int] = {}
            for j in viables:
                c = ordenadas[j]
                por_clave[c["clave"]] = max(por_clave.get(c["clave"], 0), c["creditos"])
            posibles = creditos + sum(por_clave.values())
            if any(posibles < r["creditos"] for r in minimos):
                return False
        return True

    def cota(valor: float, viables: list[int]) -> float:
        """Cota superior: a lo más una sección por materia, solo valores positivos."""
        mejor_por_clave: dict[str, float] = {}
        for j in viables:
            v = valores[j]
            if v > mejor_por_clave.get(ordenadas[j]["clave"], 0.0):
                mejor_por_clave[ordenadas[j]["clave"]] = v
        return valor + sum(mejor_por_clave.values())

    def explorar(elegidas: list[dict], valor: float, creditos: int, viables: list[int]) -> None:
        est["nodos"] += 1
        if est["nodos"] > MAX_NODOS_BACKTRACKING:
            raise _LimiteNodos
        if valor > est["mejor_valor"] and cumple_completo(elegidas):
            est["mejor_valor"] = valor
            est["mejor"] = list(elegidas)
        if not alcanzable(elegidas, creditos, viables):
            est["podas_factibilidad"] += 1
            return
        if poda_cota and cota(valor, viables) <= est["mejor_valor"]:
            est["podas_cota"] += 1
            return
        for pos, j in enumerate(viables):
            if poda_cota and valores[j] <= 0 and not exigen_negativas:
                est["podas_cota"] += 1
                continue
            clase = ordenadas[j]
            nuevas = elegidas + [clase]
            resto = viables[pos + 1:]
            siguientes = [k for k in resto if _puede_agregar(ordenadas[k], nuevas, plan)]
            est["podas_factibilidad"] += len(resto) - len(siguientes)
            explorar(nuevas, valor + valores[j], creditos + clase["creditos"], siguientes)

    inicial = [j for j in range(len(ordenadas)) if _puede_agregar(ordenadas[j], [], plan)]
    est["podas_factibilidad"] += len(ordenadas) - len(inicial)
    completo = True
    try:
        explorar([], 0.0, 0, inicial)
    except _LimiteNodos:
        completo = False

    resultado = _resultado(nombre, est["mejor"], est["nodos"], blandas)
    resultado["nodos_explorados"] = est["nodos"]
    resultado["podas_factibilidad"] = est["podas_factibilidad"]
    resultado["podas_cota"] = est["podas_cota"]
    resultado["optimo_garantizado"] = completo
    return resultado


def horario_backtracking_sin_cota(
    candidatas: list[dict],
    plan: list[dict] | None = None,
    requisitos: list[dict] | None = None,
    blandas: list[dict] | None = None,
    minimos: list[dict] | None = None,
) -> dict:
    """Backtracking que solo poda por factibilidad (para medir el efecto de la cota)."""
    return horario_backtracking(
        candidatas, plan, requisitos, blandas, minimos, poda_cota=False
    )


ESTRATEGIAS = {
    "fuerza_bruta": horario_fuerza_bruta,
    "voraz": horario_voraz,
    "backtracking": horario_backtracking,
    "backtracking_sin_cota": horario_backtracking_sin_cota,
}


def resolver(
    estrategia: str,
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
    minimos = [r for r in reglas if _clase(r) == "minimo"]

    resultado = ESTRATEGIAS[estrategia](
        candidatas, plan=plan, requisitos=requisitos, blandas=blandas, minimos=minimos
    )
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
            " Si usaste 'min_creditos', puede que las secciones disponibles no "
            "alcancen ese mínimo sin conflictos."
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
    nrcs: list[str] | None = None,
    restricciones: list[dict] | None = None,
) -> dict:
    """Arma un horario sin conflictos maximizando el valor total.

    estrategia: "backtracking" (óptima, con poda por cota: la recomendada),
        "fuerza_bruta" (óptima, solo n chico), "voraz" (rápida, aproximada) o
        "backtracking_sin_cota" (óptima; solo poda por factibilidad, para comparar).
        Si 'optimo_garantizado' es false, el backtracking llegó a su tope de nodos.
    nrcs: NRC candidatos (si se omite, usa todas las clases del catálogo).
    restricciones: lista de restricciones del catálogo (ver listar_tipos_restriccion),
        por ejemplo {"tipo": "excluir_dias", "dureza": "dura", "dias": ["M", "J"]}.
        El tope y el mínimo de créditos también son restricciones: "max_creditos" y
        "min_creditos" (sin ninguna de las dos, los créditos no tienen límite).
    La respuesta incluye 'restricciones_aplicadas' (eco de lo interpretado) y
    'descartados_por_filtro' (qué NRC eliminó cada filtro) para ajustar si no hay solución.
    Con dureza "blanda" una restricción nunca descarta nada: solo suma o resta puntos
    según 'peso' (0 a 1, por omisión 0.5). 'incluir_materia' con dureza "dura" obliga a
    que el horario tenga esa materia ('requisitos' indica cuántas secciones sobreviven).
    TONO DEL USUARIO: la dureza la decide el CONTENIDO ("no puedo", "nunca", una razón
    concreta como trabajo o transporte => "dura"); la importancia de una restricción
    "blanda" la decide el TONO, con el campo 'importancia': "ligera" ("si se puede",
    "me da igual"), "normal" (sin énfasis), "fuerte" ("de verdad prefiero", "evita")
    o "casi_obligatoria" ("lo necesito", "no quiero ni verlo"; solo se viola si una
    restricción dura lo obliga). No uses 'importancia' en restricciones duras y no la
    mezcles con 'peso'. Si dudas entre dura y blanda, pregunta al usuario.
    'violaciones' lista qué preferencias blandas quedaron incumplidas, en qué NRC y
    cuántos puntos costó: úsala para explicar los tradeoffs de cada plan.
    """
    return resolver(estrategia, nrcs, restricciones)

if __name__ == "__main__":
    mcp.run()
