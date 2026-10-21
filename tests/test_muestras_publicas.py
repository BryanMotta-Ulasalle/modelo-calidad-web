"""Regresiones con capturas reales de una página pública W3C.

Los archivos son muestras estáticas para compartir, no mediciones del portal de tesis.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BASE = RAIZ / "datos" / "muestras_publicas"
sys.path.insert(0, str(RAIZ / "src"))

from modelo_calidad_web.importacion import ErrorImportacion, importar_archivo  # noqa: E402


def leer(nombre):
    return json.loads((BASE / nombre).read_text(encoding="utf-8"))


def comprobar_integridad(test, fuente, lote, manifiesto=None):
    bytes_fuente = (BASE / fuente).read_bytes()
    salida = leer(lote)
    test.assertEqual(salida["textoOriginal"].encode("utf-8"), bytes_fuente)
    test.assertEqual(salida["sha256Original"], hashlib.sha256(bytes_fuente).hexdigest())
    test.assertEqual(salida["entradaOriginal"], json.loads(bytes_fuente))
    test.assertEqual(salida["versionCatalogoMapeos"], "1.1.0")
    if manifiesto:
        test.assertEqual(leer(manifiesto)["sha256Fuente"], hashlib.sha256(bytes_fuente).hexdigest())
    for resultado in salida["resultados"]:
        test.assertIsNone(resultado["estadoNormalizado"])
        test.assertIsNone(resultado["prioridad"])
    return salida


class MuestrasPublicasTest(unittest.TestCase):
    def test_wave_transcripcion_tiene_evidencia_y_dos_ubicaciones_reales(self):
        raw = leer("wave_extension_raw.json")
        transcripcion = leer("wave_transcripcion_manual_v1.json")
        lote = comprobar_integridad(self, "wave_transcripcion_manual_v1.json", "wave_importado.json")
        manifiesto = leer("wave_procedimiento.json")
        self.assertEqual(raw["statistics"]["allitemcount"], 82)
        self.assertEqual({categoria: raw["statistics"][categoria]
                          for categoria in ("error", "contrast", "alert", "feature", "structure")},
                         {"error": 37, "contrast": 2, "alert": 35, "feature": 5, "structure": 3})
        self.assertEqual(len(transcripcion["resultados"]), len(lote["resultados"]))
        self.assertEqual([r["identificadorOrigen"] for r in lote["resultados"]], ["contrast", "alt_missing"])
        self.assertEqual(lote["versionHerramienta"], manifiesto["extensionVersion"])
        self.assertEqual(datetime.fromisoformat(lote["fechaHora"].replace("Z", "+00:00")),
                         datetime.fromisoformat(transcripcion["captura"]["fechaHora"].replace("Z", "+00:00")))
        self.assertEqual(manifiesto["sha256Fuente"],
                         hashlib.sha256((BASE / "wave_extension_raw.json").read_bytes()).hexdigest())
        for entrada, resultado in zip(transcripcion["resultados"], lote["resultados"]):
            categoria = "contrast" if entrada["identificador"] == "contrast" else "error"
            fuente = raw["categories"][categoria]["items"][entrada["identificador"]]
            self.assertIn(entrada["ubicacion"], fuente["xpaths"])
            self.assertEqual(resultado["ubicacionElemento"], entrada["ubicacion"])
            self.assertEqual(resultado["datosOriginales"], entrada)
            self.assertTrue((BASE / entrada["evidencia"]["referenciaCaptura"]).is_file())

    def test_axe_compara_reglas_nodos_y_procedencia(self):
        raw = leer("axe_core_raw.json")
        lote = comprobar_integridad(self, "axe_core_raw.json", "axe_importado.json", "axe_procedimiento.json")
        candidatos = [(grupo, indice, item) for grupo in ("violations", "incomplete")
                      for indice, item in enumerate(raw[grupo])]
        self.assertEqual([len(raw[grupo]) for grupo in ("violations", "incomplete", "passes", "inapplicable")],
                         [7, 1, 22, 65])
        self.assertEqual(len(candidatos), 8)
        self.assertEqual(sum(len(item["nodes"]) for _, _, item in candidatos), 69)
        self.assertEqual([r["identificadorOrigen"] for r in lote["resultados"]],
                         [item["id"] for _, _, item in candidatos])
        self.assertEqual(lote["versionHerramienta"], raw["testEngine"]["version"])
        self.assertEqual(lote["contexto"]["ejecutorDeclarado"], "playwright")
        self.assertEqual(lote["contexto"]["evidenciaEjecucion"]["tipo"], "manifiesto_vinculado_por_sha256")
        self.assertEqual(raw["testRunner"]["name"], "axe")
        for (grupo, indice, fuente), resultado in zip(candidatos, lote["resultados"]):
            self.assertEqual(resultado["rutaOrigen"], f"/{grupo}/{indice}")
            self.assertEqual(resultado["datosOriginales"], fuente)
            self.assertEqual(resultado["evidencia"]["nodes"], fuente["nodes"])
            self.assertEqual(resultado["ubicacionElemento"], raw["url"])
        solo_declaracion = importar_archivo(BASE / "axe_core_raw.json", "axe-core-playwright", "EVAL", "MOD",
                                           ejecutor="playwright")
        self.assertEqual(solo_declaracion.contexto["ejecutorDeclarado"], "playwright")
        self.assertNotIn("evidenciaEjecucion", solo_declaracion.contexto)

    def test_lighthouse_compara_cinco_metricas_y_conserva_auditorias(self):
        raw = leer("lighthouse_result_raw.json")
        lote = comprobar_integridad(self, "lighthouse_result_raw.json", "lighthouse_importado.json",
                                    "lighthouse_procedimiento.json")
        metricas = [ref["id"] for ref in raw["categories"]["performance"]["auditRefs"]
                    if ref.get("group") == "metrics"]
        self.assertEqual(len(raw["audits"]), 49)
        self.assertEqual(len(raw["categories"]["performance"]["auditRefs"]), 49)
        self.assertEqual(len(metricas), 5)
        self.assertEqual([r["identificadorOrigen"] for r in lote["resultados"]], metricas)
        self.assertEqual(lote["versionHerramienta"], raw["lighthouseVersion"])
        for resultado in lote["resultados"]:
            fuente = raw["audits"][resultado["identificadorOrigen"]]
            self.assertEqual(resultado["datosOriginales"], fuente)
            self.assertEqual(resultado["valorOriginal"], fuente["numericValue"])
            self.assertEqual(resultado["unidadOriginal"], fuente["numericUnit"])
            self.assertEqual(resultado["ubicacionElemento"], raw["finalDisplayedUrl"])

    def test_axe_rechaza_manifiesto_con_hash_diferente(self):
        manifiesto = leer("axe_procedimiento.json")
        manifiesto["sha256Fuente"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "manifiesto.json"
            ruta.write_text(json.dumps(manifiesto), encoding="utf-8")
            with self.assertRaises(ErrorImportacion) as contexto:
                importar_archivo(BASE / "axe_core_raw.json", "axe-core-playwright", "EVAL", "MOD",
                                ejecutor="playwright", manifiesto_procedimiento=ruta)
            self.assertEqual(contexto.exception.codigo, "FORMATO")

    def test_axe_reporta_sin_mapeo_para_id_observado_si_falta_del_catalogo(self):
        catalogo = json.loads((RAIZ / "src" / "modelo_calidad_web" / "catalogos" /
                               "mapeos_fuentes_v1.json").read_text(encoding="utf-8"))
        del catalogo["mapeos"]["axe-core-playwright"]["html-has-lang"]
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "catalogo.json"
            ruta.write_text(json.dumps(catalogo), encoding="utf-8")
            with self.assertRaises(ErrorImportacion) as contexto:
                importar_archivo(BASE / "axe_core_raw.json", "axe-core-playwright", "EVAL", "MOD",
                                ejecutor="playwright", catalogo_mapeos=ruta)
            self.assertEqual(contexto.exception.codigo, "SIN_MAPEO")
            self.assertIn("html-has-lang", str(contexto.exception))


if __name__ == "__main__":
    unittest.main()
