import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from modelo_calidad_web.importacion import ErrorImportacion, importar_archivo, importar_datos  # noqa: E402
from modelo_calidad_web.main import main  # noqa: E402


CASOS = (
    ("wave-extension-captura-v1", "wave_captura_controlada_v1.json", "A-04"),
    ("axe-core-playwright", "axe_core_playwright_controlado.json", "U-02"),
    ("lighthouse-result", "lighthouse_result_controlado.json", "P-02"),
)


class ImportacionTest(unittest.TestCase):
    def cargar(self, nombre):
        ruta = RAIZ / "datos" / "ejemplos" / nombre
        return json.loads(ruta.read_text(encoding="utf-8"))

    def importar(self, datos, formato):
        return importar_datos(datos, formato, "EVAL-PRUEBA-002", "MOD-INICIO",
                             ejecutor="playwright" if formato == "axe-core-playwright" else None)

    def assert_codigo(self, codigo, datos, formato):
        with self.assertRaises(ErrorImportacion) as contexto:
            self.importar(datos, formato)
        self.assertEqual(contexto.exception.codigo, codigo)

    def test_positivos_tres_formatos_y_conservacion_byte_a_byte(self):
        for formato, nombre, indicador in CASOS:
            with self.subTest(formato=formato):
                ruta = RAIZ / "datos" / "ejemplos" / nombre
                bytes_originales = ruta.read_bytes()
                lote = importar_archivo(ruta, formato, "EVAL-PRUEBA-002", "MOD-INICIO",
                                        ejecutor="playwright" if formato == "axe-core-playwright" else None)
                self.assertEqual(lote.entrada_original, json.loads(bytes_originales))
                self.assertEqual(lote.texto_original.encode("utf-8"), bytes_originales)
                self.assertEqual(lote.sha256_original, hashlib.sha256(bytes_originales).hexdigest())
                self.assertEqual(lote.version_catalogo_mapeos, "1.1.0")
                self.assertEqual(lote.id_evaluacion, "EVAL-PRUEBA-002")
                self.assertEqual(lote.id_modulo_vista, "MOD-INICIO")
                self.assertEqual(len(lote.resultados), 1)
                self.assertEqual(lote.resultados[0].id_indicador, indicador)
                self.assertIsNone(lote.resultados[0].estado_normalizado)
                self.assertIsNone(lote.resultados[0].prioridad)
                self.assertTrue(lote.contexto)
                self.assertTrue(lote.version_herramienta)

    def test_wave_formato_incorrecto(self):
        datos = self.cargar(CASOS[0][1])
        datos["procedencia"] = "automatica"
        self.assert_codigo("FORMATO", datos, CASOS[0][0])

    def test_wave_evidencia_insuficiente(self):
        datos = self.cargar(CASOS[0][1])
        datos["resultados"][0]["evidencia"]["referenciaCaptura"] = ""
        self.assert_codigo("DATOS_INSUFICIENTES", datos, CASOS[0][0])

    def test_wave_identificador_sin_mapeo(self):
        datos = self.cargar(CASOS[0][1])
        datos["resultados"][0]["identificador"] = "wave-desconocido"
        self.assert_codigo("SIN_MAPEO", datos, CASOS[0][0])

    def test_axe_formato_incorrecto(self):
        datos = self.cargar(CASOS[1][1])
        datos["violations"] = {}
        self.assert_codigo("FORMATO", datos, CASOS[1][0])

    def test_axe_datos_insuficientes(self):
        datos = self.cargar(CASOS[1][1])
        datos["violations"][0]["nodes"] = []
        self.assert_codigo("DATOS_INSUFICIENTES", datos, CASOS[1][0])

    def test_axe_nodo_sin_selector(self):
        datos = self.cargar(CASOS[1][1])
        datos["violations"][0]["nodes"][0]["target"] = []
        self.assert_codigo("DATOS_INSUFICIENTES", datos, CASOS[1][0])

    def test_axe_identificador_sin_mapeo(self):
        datos = self.cargar(CASOS[1][1])
        datos["violations"][0]["id"] = "regla-desconocida"
        self.assert_codigo("SIN_MAPEO", datos, CASOS[1][0])

    def test_axe_incomplete_es_alerta_sin_clasificacion(self):
        datos = self.cargar(CASOS[1][1])
        datos["incomplete"] = [datos["violations"].pop()]
        lote = self.importar(datos, CASOS[1][0])
        self.assertEqual(lote.resultados[0].tipo_resultado.value, "alerta")
        self.assertEqual(lote.resultados[0].estado_original, "incomplete")
        self.assertIsNone(lote.resultados[0].estado_normalizado)

    def test_axe_exige_declaracion_externa_de_playwright(self):
        datos = self.cargar(CASOS[1][1])
        with self.assertRaises(ErrorImportacion) as contexto:
            importar_datos(datos, CASOS[1][0], "EVAL", "MOD")
        self.assertEqual(contexto.exception.codigo, "DATOS_INSUFICIENTES")

    def test_lighthouse_formato_incorrecto(self):
        datos = self.cargar(CASOS[2][1])
        datos["audits"]["largest-contentful-paint"]["numericValue"] = "3200"
        self.assert_codigo("FORMATO", datos, CASOS[2][0])

    def test_lighthouse_datos_insuficientes(self):
        datos = self.cargar(CASOS[2][1])
        del datos["audits"]["largest-contentful-paint"]["numericValue"]
        self.assert_codigo("DATOS_INSUFICIENTES", datos, CASOS[2][0])

    def test_lighthouse_identificador_sin_mapeo(self):
        datos = self.cargar(CASOS[2][1])
        datos["categories"]["performance"]["auditRefs"][0]["id"] = "metrica-nueva"
        self.assert_codigo("SIN_MAPEO", datos, CASOS[2][0])

    def test_lighthouse_conserva_unidad_sin_convertir(self):
        lote = self.importar(self.cargar(CASOS[2][1]), CASOS[2][0])
        resultado = lote.resultados[0]
        self.assertEqual(resultado.valor_original, 3200)
        self.assertEqual(resultado.unidad_original, "millisecond")
        self.assertIsNone(resultado.estado_normalizado)

    def test_catalogo_mapeos_rechaza_dimension_incoherente(self):
        datos = self.cargar(CASOS[0][1])
        ruta_catalogo = RAIZ / "src" / "modelo_calidad_web" / "catalogos" / "mapeos_fuentes_v1.json"
        catalogo = json.loads(ruta_catalogo.read_text(encoding="utf-8"))
        catalogo["mapeos"]["wave-extension-captura-v1"]["contrast"]["dimension"] = "D-RE"
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "mapeos.json"
            ruta.write_text(json.dumps(catalogo), encoding="utf-8")
            with self.assertRaises(ErrorImportacion) as contexto:
                importar_datos(datos, CASOS[0][0], "EVAL", "MOD", catalogo_mapeos=ruta)
            self.assertEqual(contexto.exception.codigo, "FORMATO")

    def test_cli_crea_salida_y_no_sobrescribe(self):
        ruta = RAIZ / "datos" / "ejemplos" / CASOS[0][1]
        with tempfile.TemporaryDirectory() as temporal:
            salida = Path(temporal) / "lote.json"
            argumentos = ["importar", str(ruta), "--formato", CASOS[0][0],
                          "--id-evaluacion", "EVAL-PRUEBA-002", "--id-modulo-vista", "MOD-INICIO",
                          "--salida", str(salida)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(argumentos), 0)
            contenido = json.loads(salida.read_text(encoding="utf-8"))
            self.assertEqual(contenido["resultados"][0]["estadoNormalizado"], None)
            self.assertEqual(contenido["textoOriginal"].encode("utf-8"), ruta.read_bytes())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(argumentos), 1)

    def test_json_invalido_y_copia_no_mutada(self):
        datos = self.cargar(CASOS[0][1])
        original = copy.deepcopy(datos)
        self.importar(datos, CASOS[0][0])
        self.assertEqual(datos, original)
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "mal.json"
            ruta.write_text("{", encoding="utf-8")
            with self.assertRaises(ErrorImportacion) as contexto:
                importar_archivo(ruta, CASOS[0][0], "EVAL", "MOD")
            self.assertEqual(contexto.exception.codigo, "FORMATO")


if __name__ == "__main__":
    unittest.main()
