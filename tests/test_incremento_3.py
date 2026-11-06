"""Cierre operativo: cobertura, versiones concretas y recorridos de extremo a extremo."""

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from modelo_calidad_web.importacion import ErrorImportacion, importar_archivo, importar_datos
from modelo_calidad_web.main import main
from modelo_calidad_web.procesamiento import clasificar_lote, clasificar_archivo
from modelo_calidad_web.procesamiento.motor import cargar_reglas


BASE = RAIZ / "datos/muestras_publicas_incremento3_verificadas"


def leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


class IncrementoTresTest(unittest.TestCase):
    def importar(self, datos, formato="lighthouse-result"):
        return importar_datos(datos, formato, "EVAL-SIMULADA", "VISTA-SIMULADA", perfil="incremento-3",
                              ejecutor="playwright" if formato == "axe-core-playwright" else None)

    def fuente_lh(self):
        return leer(BASE / "lighthouse_12_raw.json")

    def test_catalogo_cubre_19_indicadores_y_p06_es_contextual(self):
        catalogo = leer(RAIZ / "src/modelo_calidad_web/catalogos/mapeos_fuentes_v2.json")
        cubiertos = {v["indicador"] for formato in catalogo["mapeos"].values() for v in formato.values()}
        esperados = {f"A-{i:02}" for i in range(1, 10)} | {f"P-{i:02}" for i in range(1, 6)} | {f"U-{i:02}" for i in range(1, 6)}
        self.assertEqual(cubiertos, esperados)
        self.assertNotIn("P-06", cubiertos)
        reglas, _ = cargar_reglas()
        self.assertEqual(reglas["version"], "1.0.0")

    def test_wave_las_seis_categorias_no_se_convierten_todas_en_hallazgos(self):
        fuente = leer(RAIZ / "datos/ejemplos/wave_captura_controlada_v2.json")
        salida = clasificar_lote(self.importar(fuente, "wave-extension-captura-v2"))
        esperados = [("desfavorable", "alta"), ("desfavorable", "alta"),
                     ("requiere_revision", "revision"), (None, None), (None, None), (None, None)]
        self.assertEqual([(r.decision.estado_normalizado, r.decision.prioridad) for r in salida.resultados], esperados)
        self.assertEqual([r.origen.tipo_resultado.value for r in salida.resultados],
                         ["hallazgo", "hallazgo", "alerta", "evidencia_contextual", "evidencia_contextual", "evidencia_contextual"])
        self.assertEqual(salida.entrada_importada.entrada_original, fuente)

    def test_wave_no_fabrica_un_valor_para_contexto_nulo(self):
        fuente = leer(RAIZ / "datos/ejemplos/wave_captura_controlada_v2.json")
        fuente["resultados"] = [fuente["resultados"][3]]
        fuente["resultados"][0]["valor"] = None
        r = clasificar_lote(self.importar(fuente, "wave-extension-captura-v2")).resultados[0]
        self.assertIsNone(r.origen.valor_original)
        self.assertIsNone(r.decision.estado_normalizado)

    def test_wave_documentado_v2_vincula_categorias_a_evidencia_preexistente(self):
        ruta = BASE / "wave_captura_documentada_v2.json"
        fuente, manifiesto = leer(ruta), leer(BASE / "wave_procedimiento.json")
        raw_ruta = RAIZ / "datos/muestras_publicas/wave_extension_raw.json"
        raw = leer(raw_ruta)
        self.assertEqual(manifiesto["sha256Fuente"], hashlib.sha256(ruta.read_bytes()).hexdigest())
        self.assertEqual(manifiesto["sha256ArchivoInternoOriginal"], hashlib.sha256(raw_ruta.read_bytes()).hexdigest())
        for fila in fuente["resultados"]:
            item = raw["categories"][fila["categoria"]]["items"][fila["identificador"]]
            self.assertIn(fila["ubicacion"], item["xpaths"])
            self.assertTrue((BASE / fila["evidencia"]["referenciaCaptura"]).is_file())
        salida = clasificar_lote(self.importar(fuente, "wave-extension-captura-v2"))
        self.assertEqual([r.decision.estado_normalizado for r in salida.resultados],
                         ["desfavorable", "desfavorable", "requiere_revision", None, None])
        self.assertEqual(salida.entrada_importada.procedencia, "captura_documentada_asistida")

    def test_wave_categoria_incoherente_o_id_desconocido_se_rechazan(self):
        base = leer(RAIZ / "datos/ejemplos/wave_captura_controlada_v2.json")
        for clave, valor, codigo in (("categoria", "alert", "FORMATO"), ("identificador", "desconocido", "SIN_MAPEO")):
            with self.subTest(clave=clave):
                datos = copy.deepcopy(base)
                datos["resultados"][0][clave] = valor
                with self.assertRaises(ErrorImportacion) as error:
                    self.importar(datos, "wave-extension-captura-v2")
                self.assertEqual(error.exception.codigo, codigo)

    def test_axe_nuevos_ids_en_cuatro_grupos_con_mapeos_y_dimensiones_exactos(self):
        base = leer(RAIZ / "datos/ejemplos/axe_core_playwright_controlado.json")
        elemento = base["violations"][0]
        for id_, indicador in (("document-title", "A-05"), ("aria-valid-attr", "A-08"),
                               ("aria-valid-attr-value", "A-08"), ("frame-focusable-content", "A-09"),
                               ("target-size", "U-03")):
            for grupo, estado in (("violations", "desfavorable"), ("incomplete", "requiere_revision"),
                                  ("passes", "favorable"), ("inapplicable", "no_evaluado")):
                with self.subTest(id=id_, grupo=grupo):
                    fuente = copy.deepcopy(base)
                    for g in ("violations", "incomplete", "passes", "inapplicable"):
                        fuente[g] = []
                    regla = copy.deepcopy(elemento)
                    regla.update(id=id_, impact="serious")
                    if grupo == "inapplicable":
                        regla["nodes"] = []
                    fuente[grupo] = [regla]
                    lote = self.importar(fuente, "axe-core-playwright")
                    r = clasificar_lote(lote).resultados[0]
                    self.assertEqual(r.origen.id_indicador, indicador)
                    self.assertEqual(r.origen.id_dimension, "D-US" if indicador == "U-03" else "D-AC")
                    self.assertEqual(r.decision.estado_normalizado, estado)
                    self.assertEqual(lote.herramienta, "axe-core")

    def test_axe_selectores_anidados_en_violations_e_incomplete(self):
        base = leer(RAIZ / "datos/ejemplos/axe_core_playwright_controlado.json")
        for grupo in ("violations", "incomplete"):
            fuente = copy.deepcopy(base)
            regla = fuente["violations"].pop()
            regla["nodes"][0]["target"] = [["#frame", ["#shadow", "button"]]]
            fuente[grupo] = [regla]
            salida = clasificar_lote(self.importar(fuente, "axe-core-playwright"))
            self.assertEqual(salida.resultados[0].origen.datos_originales, regla)

    def test_auditorias_usabilidad_cuatro_situaciones_sin_score_inferido(self):
        for id_, indicador in (("viewport", "U-01"), ("paste-preventing-inputs", "U-04"), ("errors-in-console", "U-05")):
            for modo, score, esperado in (("binary" if id_ != "viewport" else "metricSavings", 1, "favorable"),
                                         ("binary" if id_ != "viewport" else "metricSavings", 0, "requiere_revision" if id_ == "errors-in-console" else "desfavorable"),
                                         ("notApplicable", None, "no_evaluado"), ("error", None, "no_evaluado")):
                with self.subTest(id=id_, modo=modo, score=score):
                    datos = self.fuente_lh()
                    datos["audits"][id_].update(score=score, scoreDisplayMode=modo)
                    if score == 0 and id_ != "viewport":
                        datos["audits"][id_]["details"]["items"] = [{"descripcion": "EVIDENCIA SIMULADA PARA ESTE CASO DE PRUEBA"}]
                    r = next(r for r in clasificar_lote(self.importar(datos)).resultados if r.origen.id_indicador == indicador)
                    self.assertEqual(r.decision.estado_normalizado, esperado)
                    self.assertEqual(r.origen.valor_original, score)

    def test_score_booleano_fraccionario_texto_o_modo_no_admitido_no_se_interpreta(self):
        for score in (True, False, 0.5, "1", None):
            datos = self.fuente_lh()
            datos["audits"]["paste-preventing-inputs"]["score"] = score
            with self.subTest(score=score), self.assertRaises(ErrorImportacion):
                self.importar(datos)
        datos = self.fuente_lh()
        datos["audits"]["paste-preventing-inputs"]["scoreDisplayMode"] = "numeric"
        with self.assertRaises(ErrorImportacion):
            self.importar(datos)

    def test_auditoria_ausente_no_crea_resultado_ni_favorable(self):
        datos = self.fuente_lh()
        del datos["audits"]["paste-preventing-inputs"]
        salida = clasificar_lote(self.importar(datos))
        self.assertFalse(any(r.origen.id_indicador == "U-04" for r in salida.resultados))
        fila = next(f for f in salida.cobertura_indicadores if f.id_indicador == "U-04")
        self.assertEqual(fila.situacion, "sin_resultados_en_fuente")

    def test_auditoria_sin_referencia_de_ejecucion_se_rechaza(self):
        datos = self.fuente_lh()
        for categoria in datos["categories"].values():
            categoria["auditRefs"] = [r for r in categoria["auditRefs"] if r["id"] != "viewport"]
        with self.assertRaises(ErrorImportacion):
            self.importar(datos)

    def test_fallo_de_pegado_o_consola_sin_evidencia_no_se_admite(self):
        for id_ in ("paste-preventing-inputs", "errors-in-console"):
            datos = self.fuente_lh()
            datos["audits"][id_]["score"] = 0
            with self.subTest(id=id_), self.assertRaises(ErrorImportacion) as error:
                self.importar(datos)
            self.assertEqual(error.exception.codigo, "DATOS_INSUFICIENTES")

    def test_viewport_version_13_no_se_sustituye_por_insight(self):
        datos = leer(BASE / "lighthouse_13_raw.json")
        salida = clasificar_lote(self.importar(datos))
        self.assertFalse(any(r.origen.id_indicador == "U-01" for r in salida.resultados))
        fila = next(f for f in salida.cobertura_indicadores if f.id_indicador == "U-01")
        self.assertIn("no_se_asume_equivalencia", fila.motivo)
        datos["audits"]["viewport"] = self.fuente_lh()["audits"]["viewport"]
        with self.assertRaises(ErrorImportacion) as error:
            self.importar(datos)
        self.assertEqual(error.exception.codigo, "VERSION_NO_ADMITIDA")

    def test_bloqueo_http_no_se_clasifica_como_vista_esperada(self):
        datos = self.fuente_lh()
        datos["audits"]["http-status-code"]["score"] = 0
        with self.assertRaises(ErrorImportacion) as error:
            self.importar(datos)
        self.assertEqual(error.exception.codigo, "DATOS_INSUFICIENTES")

    def test_catalogo_ampliado_incompleto_no_produce_error_sin_categoria(self):
        mapa = leer(RAIZ / "src/modelo_calidad_web/catalogos/mapeos_fuentes_v2.json")
        del mapa["mapeos"]["wave-extension-captura-v2"]["alt"]["categoria"]
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "mapa.json"
            ruta.write_text(json.dumps(mapa), encoding="utf-8")
            with self.assertRaises(ErrorImportacion) as error:
                importar_datos(self.fuente_lh(), "lighthouse-result", "E", "V", perfil="incremento-3", catalogo_mapeos=ruta)
            self.assertEqual(error.exception.codigo, "FORMATO")

    def test_importacion_no_acepta_claves_repetidas_ni_infinito_en_contexto(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "mal.json"
            for texto in ('{"a":1,"a":2}', '{"configSettings":{"x":1e999}}'):
                ruta.write_text(texto, encoding="utf-8")
                with self.subTest(texto=texto), self.assertRaises(ErrorImportacion) as error:
                    importar_archivo(ruta, "lighthouse-result", "E", "V", perfil="incremento-3")
                self.assertEqual(error.exception.codigo, "FORMATO")

    def test_conversion_segundos_milisegundos_en_recorrido_importar_clasificar(self):
        for unidad, valor in (("second", 3.2), ("millisecond", 3200)):
            with self.subTest(unidad=unidad):
                fuente = self.fuente_lh()
                fuente["audits"]["largest-contentful-paint"].update(numericValue=valor, numericUnit=unidad)
                salida = clasificar_lote(self.importar(fuente))
                r = next(r for r in salida.resultados if r.origen.id_indicador == "P-02")
                self.assertEqual(r.decision.estado_normalizado, "intermedio")
                self.assertEqual(r.decision.valor_normalizado, 3200)
                self.assertEqual(r.origen.valor_original, valor)
                self.assertEqual(r.origen.unidad_original, unidad)

    def test_muestras_autenticas_y_manifiestos_intactos_sin_navegador_en_pruebas(self):
        for nombre, formato, cantidad in (("axe_core", "axe-core-playwright", 13),
                                         ("lighthouse_12", "lighthouse-result", 8),
                                         ("lighthouse_13", "lighthouse-result", 7)):
            with self.subTest(muestra=nombre):
                ruta = BASE / (nombre + "_raw.json")
                manifiesto = leer(BASE / ("axe_procedimiento.json" if nombre == "axe_core" else nombre + "_procedimiento.json"))
                self.assertEqual(hashlib.sha256(ruta.read_bytes()).hexdigest(), manifiesto["sha256Fuente"])
                fuente = leer(ruta)
                self.assertEqual(manifiesto["urlFinal"], fuente.get("url", fuente.get("finalDisplayedUrl")))
                self.assertEqual(manifiesto["urlFinal"], "https://example.com/")
                lote = importar_archivo(ruta, formato, "EVAL-PUBLICA-INC3", "EXAMPLE-PUBLICA",
                                       perfil="incremento-3", ejecutor="playwright" if nombre == "axe_core" else None,
                                       manifiesto_procedimiento=BASE / "axe_procedimiento.json" if nombre == "axe_core" else None)
                salida = clasificar_lote(lote)
                self.assertEqual(len(salida.resultados), cantidad)
                self.assertEqual(salida.entrada_importada.texto_original.encode("utf-8"), ruta.read_bytes())
                self.assertEqual(len(salida.cobertura_indicadores), 20)
                if nombre.startswith("lighthouse"):
                    self.assertEqual(fuente["audits"]["http-status-code"]["score"], 1)
                    for r in salida.resultados:
                        if r.origen.id_indicador.startswith("U-"):
                            self.assertEqual(r.decision.estado_normalizado, "favorable")

    def test_cli_perfil_nuevo_con_archivo_intermedio_y_salida_nuevos(self):
        with tempfile.TemporaryDirectory() as temporal:
            entrada, salida = Path(temporal) / "importado.json", Path(temporal) / "clasificado.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["importar", str(BASE / "lighthouse_12_raw.json"), "--formato", "lighthouse-result",
                                       "--perfil", "incremento-3", "--id-evaluacion", "E", "--id-modulo-vista", "V",
                                       "--salida", str(entrada)]), 0)
                self.assertEqual(main(["clasificar", str(entrada), "--salida", str(salida)]), 0)
            lote = clasificar_archivo(entrada)
            self.assertEqual(lote.version_motor, "0.3.0")
            self.assertEqual(lote.sha256_lote_importado, hashlib.sha256(entrada.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
