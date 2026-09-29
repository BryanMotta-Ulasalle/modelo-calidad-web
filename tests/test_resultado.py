import copy
import json
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from modelo_calidad_web.dominio.resultado import ResultadoNormalizado  # noqa: E402


class ResultadoNormalizadoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ruta = RAIZ / "datos" / "ejemplos" / "wave_ejemplo.json"
        cls.datos_validos = json.loads(ruta.read_text(encoding="utf-8"))

    def test_acepta_resultado_valido(self):
        resultado = ResultadoNormalizado.model_validate(self.datos_validos)
        self.assertEqual(resultado.id_indicador, "A-04")
        self.assertEqual(resultado.herramienta.value, "WAVE")

    def test_rechaza_campo_obligatorio_ausente(self):
        datos = copy.deepcopy(self.datos_validos)
        datos.pop("idEvaluacion")
        with self.assertRaises(ValidationError):
            ResultadoNormalizado.model_validate(datos)

    def test_rechaza_herramienta_no_reconocida(self):
        datos = copy.deepcopy(self.datos_validos)
        datos["herramienta"] = "Herramienta desconocida"
        with self.assertRaises(ValidationError):
            ResultadoNormalizado.model_validate(datos)

    def test_rechaza_hallazgo_sin_evidencia(self):
        datos = copy.deepcopy(self.datos_validos)
        datos["evidencia"] = None
        with self.assertRaises(ValidationError):
            ResultadoNormalizado.model_validate(datos)

    def test_rechaza_metrica_sin_unidad(self):
        ruta = RAIZ / "datos" / "ejemplos" / "lighthouse_ejemplo.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["unidad"] = None
        with self.assertRaises(ValidationError):
            ResultadoNormalizado.model_validate(datos)


if __name__ == "__main__":
    unittest.main()

