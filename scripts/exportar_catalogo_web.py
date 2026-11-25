"""Exporta clases_stub.py a web/app/catalogo.json para la interfaz web.

Solo lee clases_stub.py, no lo modifica. Se corre desde la raíz del repo:
    python scripts/exportar_catalogo_web.py
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from clases_stub import CLASES_STUB

# Solo los campos que la interfaz necesita (el JSON queda mucho más liviano).
CAMPOS = ["ciclo", "nrc", "clave", "materia", "seccion", "creditos", "cupo",
          "disponibles", "dias", "hora", "edificio", "aula", "profesor", "profesores"]

salida = [{k: c.get(k) for k in CAMPOS} for c in CLASES_STUB]
destino = RAIZ / "web" / "app" / "catalogo.json"
destino.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
print(f"{len(salida)} clases exportadas a {destino}")
