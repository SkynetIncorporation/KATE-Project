import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kate_mcp as k
from clases_stub import CLASES_STUB

PROFE = "LOPEZ"


def _con_profe(resultado):
    return any(
        PROFE.lower() in c["profesor"].lower()
        for c in CLASES_STUB if c["nrc"] in resultado["nrcs"]
    )


class RestriccionesProfesor(unittest.TestCase):
    def test_excluir_dura_descarta_al_profesor(self):
        r = k.resolver("voraz", None, [{"tipo": "excluir_profesor", "dureza": "dura", "profesor": PROFE}])
        self.assertFalse(_con_profe(r))

    def test_excluir_blanda_no_descarta_candidatas(self):
        r = k.resolver("voraz", None, [{"tipo": "excluir_profesor", "dureza": "blanda", "profesor": PROFE}])
        self.assertEqual(r["candidatas_iniciales"], r["candidatas_tras_filtros"])

    def test_incluir_dura_exige_al_profesor(self):
        for est in ("voraz", "backtracking"):
            r = k.resolver(est, None, [{"tipo": "incluir_profesor", "dureza": "dura", "profesor": PROFE}])
            self.assertTrue(_con_profe(r), est)

    def test_incluir_dura_sin_coincidencias_no_tiene_solucion(self):
        r = k.resolver("voraz", None, [{"tipo": "incluir_profesor", "dureza": "dura", "profesor": "ZZZNOEXISTE"}])
        self.assertTrue(r.get("sin_solucion"))

    def test_incluir_blanda_sin_coincidencias_reporta_violacion(self):
        r = k.resolver("voraz", None, [
            {"tipo": "incluir_profesor", "dureza": "blanda", "profesor": "ZZZNOEXISTE", "importancia": "fuerte"}
        ])
        self.assertTrue(r["nrcs"])
        self.assertEqual(r["violaciones"][0]["profesor"], "ZZZNOEXISTE")

    def test_incluir_y_excluir_duras_del_mismo_profesor_se_rechazan(self):
        with self.assertRaises(ValueError):
            k.validar_restricciones([
                {"tipo": "incluir_profesor", "dureza": "dura", "profesor": PROFE},
                {"tipo": "excluir_profesor", "dureza": "dura", "profesor": PROFE},
            ])

    def test_profesor_vacio_se_rechaza(self):
        for tipo in ("incluir_profesor", "excluir_profesor"):
            with self.assertRaises(ValueError):
                k.validar_restricciones([{"tipo": tipo, "dureza": "dura", "profesor": "  "}])


if __name__ == "__main__":
    unittest.main()
