"""Pruebas del backend con un Gemini simulado y el servidor MCP real (kate_mcp.py)."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend import server  # noqa: E402


def _llamada(nombre, args):
    parte = SimpleNamespace(function_call=SimpleNamespace(name=nombre, args=args), text=None)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[parte]))], text=None)


def _texto(txt):
    parte = SimpleNamespace(function_call=None, text=txt)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[parte]))], text=txt)


def _gemini_simulado(guion):
    pasos = iter(guion)

    async def generar(contenidos, declaraciones):
        return next(pasos)
    return generar


async def _con_sesion(coro):
    params = StdioServerParameters(command=sys.executable, args=[str(RAIZ / "kate_mcp.py")], cwd=str(RAIZ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await coro(s)


def test_responder_junta_planes_distintos_y_la_respuesta():
    manana = [{"tipo": "max_creditos", "dureza": "dura", "creditos": 20},
              {"tipo": "preferir_hora", "dureza": "blanda", "desde": "08:00", "hasta": "14:00"}]
    tarde = [{"tipo": "max_creditos", "dureza": "dura", "creditos": 16}]
    guion = [
        _llamada("armar_horario", {"estrategia": "backtracking", "restricciones": manana}),
        _llamada("armar_horario", {"estrategia": "backtracking", "restricciones": tarde}),
        _llamada("armar_horario", {"estrategia": "backtracking", "restricciones": tarde}),  # repetido
        _texto("Plan 1 prioriza la mañana; Plan 2 baja a 16 créditos."),
    ]

    async def caso(session):
        return await server.responder("20 créditos en la mañana", session, [], _gemini_simulado(guion))

    out = asyncio.run(_con_sesion(caso))
    assert out["respuesta"].startswith("Plan 1")
    assert 1 <= len(out["planes"]) <= 2          # el plan repetido no se duplica
    for i, p in enumerate(out["planes"], 1):
        assert p["nombre"] == f"Plan {i}" and p["nrcs"] and isinstance(p["sacrifica"], str)
    nrcs_catalogo = {c["nrc"] for c in json.loads((RAIZ / "web/app/catalogo.json").read_text())}
    assert all(n in nrcs_catalogo for p in out["planes"] for n in p["nrcs"])


def test_herramienta_no_permitida_y_error_de_herramienta_no_tumban_el_ciclo():
    guion = [
        _llamada("obtener_clases_disponibles", {}),                       # fuera de la lista permitida
        _llamada("armar_horario", {"estrategia": "inexistente"}),         # la herramienta falla
        _texto("No pude armar el horario."),
    ]

    async def caso(session):
        return await server.responder("hola", session, [], _gemini_simulado(guion))

    out = asyncio.run(_con_sesion(caso))
    assert out["planes"] == [] and out["respuesta"]


def test_chat_exige_el_secreto():
    from fastapi.testclient import TestClient
    server.SECRETO = "secreto-de-prueba"
    with TestClient(server.app) as cliente:
        assert cliente.get("/salud").json()["herramientas"]
        assert cliente.post("/chat", json={"texto": "hola"}).status_code == 403
        assert cliente.post("/chat", json={"texto": "hola"}, headers={"X-Kate-Secret": "otro"}).status_code == 403
