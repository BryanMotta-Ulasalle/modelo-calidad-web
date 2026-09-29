import copy
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from modelo_calidad_web.dominio.resultado import ResultadoNormalizado  # noqa: E402
from modelo_calidad_web.validacion.catalogos import (  # noqa: E402
    ErrorCatalogo,
    cargar_catalogos,
)


class CatalogosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogos = cargar_catalogos(RAIZ / "src" / "modelo_calidad_web" / "catalogos")
        ruta = RAIZ / "datos" / "ejemplos" / "wave_ejemplo.json"
        cls.datos_validos = json.loads(ruta.read_text(encoding="utf-8"))

    def test_carga_cantidades_definidas_en_el_diseno(self):
        self.assertEqual(len(self.catalogos.dimensiones), 3)
        self.assertEqual(len(self.catalogos.indicadores), 20)
        self.assertEqual(len(self.catalogos.estados), 5)
        self.assertEqual(len(self.catalogos.reglas_normalizacion), 10)

    def test_acepta_indicador_y_dimension_coherentes(self):
        resultado = ResultadoNormalizado.model_validate(self.datos_validos)
        self.catalogos.validar_resultado(resultado)

    def test_rechaza_indicador_inexistente(self):
        datos = copy.deepcopy(self.datos_validos)
        datos["idIndicador"] = "A-99"
        resultado = ResultadoNormalizado.model_validate(datos)
        with self.assertRaises(ErrorCatalogo):
            self.catalogos.validar_resultado(resultado)

    def test_rechaza_dimension_incompatible(self):
        datos = copy.deepcopy(self.datos_validos)
        datos["idDimension"] = "D-RE"
        resultado = ResultadoNormalizado.model_validate(datos)
        with self.assertRaises(ErrorCatalogo):
            self.catalogos.validar_resultado(resultado)


if __name__ == "__main__":
    unittest.main()
