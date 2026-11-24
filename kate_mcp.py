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


# ---------------------------------------------------------------------------
# Modelo del problema: selección de secciones (NRC) sin conflictos.
#   - Cada candidata tiene un valor y un costo en créditos.
#   - Dos NRC no pueden coexistir si se traslapan en día y hora,
#     o si son la misma materia (misma clave, distinta sección).
#   - La suma de créditos no puede pasar de max_creditos.
# Generaliza la mochila 0/1 (capacidad = créditos) con conflictos entre pares.
# ---------------------------------------------------------------------------

def _a_minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _intervalo(clase: dict) -> tuple[int, int]:
    inicio, fin = clase["hora"].split("-")
    return _a_minutos(inicio), _a_minutos(fin)


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


def _es_factible(subconjunto: list[dict], max_creditos: int) -> bool:
    if sum(c["creditos"] for c in subconjunto) > max_creditos:
        return False
    for a, b in combinations(subconjunto, 2):
        if hay_conflicto(a, b):
            return False
    return True


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

def horario_fuerza_bruta(candidatas: list[dict], max_creditos: int) -> dict:
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
        if not _es_factible(subconjunto, max_creditos):
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

def horario_voraz(candidatas: list[dict], max_creditos: int) -> dict:
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
        elegidas.append(clase)
        creditos += clase["creditos"]
    return _resultado("voraz", elegidas, evaluaciones)


ESTRATEGIAS = {
    "fuerza_bruta": horario_fuerza_bruta,
    "voraz": horario_voraz,
}


@mcp.tool()
def obtener_clases_disponibles() -> list[dict]:
    """Retorna todas las clases disponibles (stub con datos inventados del CUCEI)."""
    return CLASES_STUB


@mcp.tool()
def armar_horario(
    estrategia: str = "voraz",
    max_creditos: int = 30,
    nrcs: list[str] | None = None,
) -> dict:
    """Arma un horario sin conflictos maximizando el valor total.

    estrategia: "fuerza_bruta" (óptima, lenta) o "voraz" (rápida, aproximada).
    max_creditos: tope de créditos del horario.
    nrcs: NRC candidatos (si se omite, usa todas las clases del catálogo).
    """
    if estrategia not in ESTRATEGIAS:
        raise ValueError(f"Estrategia desconocida: {estrategia}. Usa {list(ESTRATEGIAS)}.")
    candidatas = [c for c in CLASES_STUB if nrcs is None or c["nrc"] in nrcs]
    return ESTRATEGIAS[estrategia](candidatas, max_creditos)


@mcp.tool()
def sumar(a: int, b: int) -> int:
    """Suma dos números."""
    return a + b

@mcp.tool()
def multiplicar(a: int, b: int) -> int:
    """Multiplica dos números."""
    return a * b

if __name__ == "__main__":
    mcp.run()
