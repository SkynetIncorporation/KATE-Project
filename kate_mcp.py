from kate_mcp.server.mcpserver import MCPServer

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


@mcp.tool()
def obtener_clases_disponibles() -> list[dict]:
    """Retorna todas las clases disponibles (stub con datos inventados del CUCEI)."""
    return CLASES_STUB


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