"""Casos del modelo: fronteras, incertidumbre, procedencia y conservación."""

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

from modelo_calidad_web.importacion import importar_datos
from modelo_calidad_web.main import main
from modelo_calidad_web.procesamiento import ErrorProcesamiento, clasificar_archivo, clasificar_lote
from modelo_calidad_web.procesamiento.modelos import LoteProcesado
from modelo_calidad_web.procesamiento.motor import json_estricto, normalizar_metrica


def ejemplo(nombre):
    return json.loads((RAIZ / "datos/ejemplos" / nombre).read_text(encoding="utf-8"))


def lote_metrica(identificador="largest-contentful-paint", valor=3200, perfil="mobile"):
    fuente = ejemplo("lighthouse_result_controlado.json")
    fuente["categories"]["performance"]["auditRefs"] = [{"id": identificador, "group": "metrics"}]
    fuente["audits"] = {identificador: {"id": identificador, "numericValue": valor,
                                      "numericUnit": "unitless" if identificador == "cumulative-layout-shift" else "millisecond"}}
    if perfil is None:
        fuente["configSettings"].pop("formFactor")
    else:
        fuente["configSettings"]["formFactor"] = perfil
    return importar_datos(fuente, "lighthouse-result", "EVAL-SIMULADA", "VISTA-SIMULADA")


def lote_axe(grupo="violations", impacto="serious", identificador="meta-viewport"):
    fuente = ejemplo("axe_core_playwright_controlado.json")
    regla = fuente["violations"].pop()
    regla["id"], regla["impact"] = identificador, impacto
    if grupo == "inapplicable":
        regla["nodes"] = []
    fuente[grupo] = [regla]
    return importar_datos(fuente, "axe-core-playwright", "EVAL-SIMULADA", "VISTA-SIMULADA", ejecutor="playwright")


class ClasificacionTest(unittest.TestCase):
    def test_fronteras_de_las_cinco_metricas_sin_redondeo(self):
        # Expectativas escritas desde el cuadro del modelo; no se leen del catálogo ejecutable.
        casos = {
            "first-contentful-paint": [(0, "favorable"), (1800, "favorable"), (1800.001, "intermedio"), (3000, "intermedio"), (3000.001, "desfavorable")],
            "largest-contentful-paint": [(2500, "favorable"), (2500.001, "intermedio"), (3200, "intermedio"), (4000, "intermedio"), (4000.001, "desfavorable")],
            "total-blocking-time": [(0, "favorable"), (200, "favorable"), (200.001, "intermedio"), (600, "intermedio"), (600.001, "desfavorable")],
            "cumulative-layout-shift": [(0.10, "favorable"), (0.100001, "intermedio"), (0.25, "intermedio"), (0.250001, "desfavorable"), (1.2, "desfavorable")],
            "speed-index": [(3400, "favorable"), (3400.001, "intermedio"), (5800, "intermedio"), (5800.001, "desfavorable")],
        }
        for indicador, valores in casos.items():
            for valor, esperado in valores:
                with self.subTest(indicador=indicador, valor=valor):
                    decision = clasificar_lote(lote_metrica(indicador, valor)).resultados[0].decision
                    self.assertEqual(decision.estado_normalizado, esperado)
                    self.assertEqual(decision.valor_normalizado, valor)
                    self.assertIsNone(decision.prioridad)

    def test_perfil_escritorio_o_ausente_no_recibe_umbrales_moviles(self):
        for metrica in ("first-contentful-paint", "largest-contentful-paint", "total-blocking-time", "speed-index"):
            for perfil in ("desktop", None, "otro"):
                with self.subTest(metrica=metrica, perfil=perfil):
                    resultado = clasificar_lote(lote_metrica(metrica, 100, perfil)).resultados[0]
                    self.assertEqual(resultado.decision.estado_normalizado, "no_evaluado")
                    self.assertEqual(resultado.decision.motivo_estado,
                                     "perfil_ausente" if perfil is None else "perfil_sin_regla_admitida")
                    self.assertEqual(resultado.origen.valor_original, 100)

    def test_cls_independiente_del_perfil_pero_conserva_su_ausencia(self):
        decision = clasificar_lote(lote_metrica("cumulative-layout-shift", 0.1, None)).resultados[0].decision
        self.assertEqual(decision.estado_normalizado, "favorable")
        self.assertIsNone(decision.condiciones["perfilObservado"])
        self.assertEqual(decision.unidad_normalizada, "unitless")

    def test_conversion_de_segundos_y_milisegundos_equivalente(self):
        self.assertEqual(normalizar_metrica(3.2, "s", "ms"), 3200)
        self.assertEqual(normalizar_metrica(3.2, "second", "ms"), 3200)
        self.assertEqual(normalizar_metrica(3200, "millisecond", "ms"), 3200)
        self.assertEqual(normalizar_metrica(0.25, "unitless", "unitless"), 0.25)

    def test_conversion_rechaza_booleanos_textos_negativos_y_no_finitos(self):
        for valor in (True, False, "3200", None, -1, float("nan"), float("inf"), 10**400):
            with self.subTest(valor=repr(valor)):
                with self.assertRaises(ErrorProcesamiento) as error:
                    normalizar_metrica(valor, "ms", "ms")
                self.assertEqual(error.exception.codigo, "DATO_INVALIDO")
        with self.assertRaises(ErrorProcesamiento):
            normalizar_metrica(1e308, "s", "ms")

    def test_conversion_rechaza_unidad_ausente_o_incompatible(self):
        for unidad in (None, "", "bytes", "unitless"):
            with self.subTest(unidad=unidad), self.assertRaises(ErrorProcesamiento) as error:
                normalizar_metrica(1, unidad, "ms")
            self.assertEqual(error.exception.codigo, "UNIDAD_NO_ADMITIDA")

    def test_metrica_negativa_rechazada_aunque_importacion_previa_la_admita(self):
        with self.assertRaises(ErrorProcesamiento) as error:
            clasificar_lote(lote_metrica(valor=-1))
        self.assertEqual(error.exception.codigo, "DATO_INVALIDO")

    def test_auditoria_con_error_o_no_aplicable_no_es_favorable(self):
        for modo, motivo in (("error", "auditoria_con_error"), ("notApplicable", "no_aplicable")):
            with self.subTest(modo=modo):
                fuente = copy.deepcopy(lote_metrica(valor=100).entrada_original)
                fuente["audits"]["largest-contentful-paint"]["scoreDisplayMode"] = modo
                lote = importar_datos(fuente, "lighthouse-result", "E", "V")
                decision = clasificar_lote(lote).resultados[0].decision
                self.assertEqual(decision.estado_normalizado, "no_evaluado")
                self.assertEqual(decision.motivo_estado, motivo)

    def test_lcp_controlado_conserva_original_y_explica_decision(self):
        lote = lote_metrica()
        antes = lote.model_dump_json()
        salida = clasificar_lote(lote)
        r = salida.resultados[0]
        self.assertEqual(r.decision.estado_normalizado, "intermedio")
        self.assertEqual(r.decision.id_regla, "RE-02")
        self.assertEqual(r.decision.valor_normalizado, 3200)
        self.assertEqual(r.origen.unidad_original, "millisecond")
        self.assertEqual(r.decision.condiciones["intermedioMax"], 4000)
        self.assertEqual(lote.model_dump_json(), antes)
        self.assertIsNone(r.origen.estado_normalizado)
        self.assertEqual(LoteProcesado.model_validate_json(salida.model_dump_json(by_alias=True)), salida)

    def test_prioridades_axe_y_dimension_usabilidad_se_conservan(self):
        for impacto, prioridad in (("critical", "critica"), ("serious", "alta"), ("moderate", "media"), ("minor", "baja")):
            with self.subTest(impacto=impacto):
                salida = clasificar_lote(lote_axe(impacto=impacto))
                r = salida.resultados[0]
                self.assertEqual(r.decision.estado_normalizado, "desfavorable")
                self.assertEqual(r.decision.prioridad, prioridad)
                self.assertEqual(r.origen.id_dimension, "D-US")
                self.assertEqual(salida.motor_fuente, "axe-core")
                self.assertEqual(salida.entrada_importada.herramienta, "axe DevTools")  # Identidad heredada intacta.

    def test_violacion_sin_impacto_no_pierde_su_estado(self):
        for impacto in (None, "desconocido"):
            with self.subTest(impacto=impacto):
                r = clasificar_lote(lote_axe(impacto=impacto)).resultados[0]
                self.assertEqual(r.decision.estado_normalizado, "desfavorable")
                self.assertIsNone(r.decision.prioridad)
                self.assertEqual(r.decision.id_regla, "AC-08")
                self.assertEqual(r.origen.valor_original, impacto)

    def test_incomplete_con_impacto_serious_sigue_pendiente(self):
        r = clasificar_lote(lote_axe("incomplete")).resultados[0]
        self.assertEqual(r.decision.estado_normalizado, "requiere_revision")
        self.assertEqual(r.decision.prioridad, "revision")
        self.assertEqual(r.decision.revision, "pendiente")
        self.assertEqual(r.origen.valor_original, "serious")

    def test_pass_e_inapplicable_proceden_del_original_sin_valores_inventados(self):
        for grupo, estado in (("passes", "favorable"), ("inapplicable", "no_evaluado")):
            with self.subTest(grupo=grupo):
                lote = lote_axe(grupo, None)
                self.assertEqual(lote.resultados, [])  # Importar conserva su contrato anterior.
                r = clasificar_lote(lote).resultados[0]
                self.assertEqual(r.decision.estado_normalizado, estado)
                self.assertEqual(r.etapa_origen, "fuente_conservada")
                self.assertIsNone(r.origen.valor_original)
                self.assertIsNone(r.decision.prioridad)
                self.assertEqual(r.origen.ruta_origen, f"/{grupo}/0")

    def test_ids_no_mapeados_en_passes_solo_quedan_en_inventario(self):
        salida = clasificar_lote(lote_axe("passes", None, "regla-fuera-catalogo"))
        self.assertEqual(salida.resultados, [])
        self.assertEqual(len(salida.fuentes_fuera_cobertura), 1)
        self.assertEqual(salida.fuentes_fuera_cobertura[0].identificador_origen, "regla-fuera-catalogo")

    def test_regla_ausente_no_se_convierte_en_pass(self):
        salida = clasificar_lote(lote_axe())
        self.assertEqual(len(salida.resultados), 1)
        self.assertFalse(any(r.origen.estado_original == "passes" for r in salida.resultados))

    def test_pass_mapeado_sin_evidencia_no_se_clasifica_como_favorable(self):
        lote = lote_axe("passes", None)
        fuente = copy.deepcopy(lote.entrada_original)
        fuente["passes"][0]["nodes"] = []
        lote = importar_datos(fuente, "axe-core-playwright", "E", "V", ejecutor="playwright")
        with self.assertRaises(ErrorProcesamiento) as error:
            clasificar_lote(lote)
        self.assertEqual(error.exception.codigo, "DATOS_INSUFICIENTES")

    def test_selectores_anidados_en_passes_se_conservan(self):
        fuente = copy.deepcopy(lote_axe("passes", None).entrada_original)
        fuente["passes"][0]["nodes"][0]["target"] = [["iframe", "#elemento"]]
        lote = importar_datos(fuente, "axe-core-playwright", "E", "V", ejecutor="playwright")
        salida = clasificar_lote(lote)
        self.assertEqual(salida.resultados[0].origen.evidencia["nodes"][0]["target"], [["iframe", "#elemento"]])

    def test_target_de_pass_debe_ser_lista_no_cadena_ni_lista_vacia(self):
        for objetivo in ("#elemento", [], [True], [[]]):
            with self.subTest(objetivo=objetivo):
                fuente = copy.deepcopy(lote_axe("passes", None).entrada_original)
                fuente["passes"][0]["nodes"][0]["target"] = objetivo
                lote = importar_datos(fuente, "axe-core-playwright", "E", "V", ejecutor="playwright")
                with self.assertRaises(ErrorProcesamiento):
                    clasificar_lote(lote)

    def test_wave_prioridad_del_catalogo_y_dos_hallazgos_no_se_fusionan(self):
        fuente = ejemplo("wave_captura_controlada_v1.json")
        segundo = copy.deepcopy(fuente["resultados"][0])
        segundo["ubicacion"] += "-otro-elemento"
        fuente["resultados"].append(segundo)
        lote = importar_datos(fuente, "wave-extension-captura-v1", "E", "V")
        salida = clasificar_lote(lote)
        self.assertEqual(len(salida.resultados), 2)
        self.assertNotEqual(salida.resultados[0].origen.id_resultado, salida.resultados[1].origen.id_resultado)
        for r in salida.resultados:
            self.assertEqual(r.decision.estado_normalizado, "desfavorable")
            self.assertEqual(r.decision.prioridad, "alta")
            self.assertTrue(r.decision.condiciones["prioridadEsDecisionDelModelo"])
            self.assertIn("convencion operativa del modelo", r.decision.motivo_prioridad)

    def test_puntuacion_compuesta_solo_contextual(self):
        lote = lote_metrica()
        fuente = copy.deepcopy(lote.entrada_original)
        fuente["categories"]["performance"]["score"] = 0.93
        salida = clasificar_lote(importar_datos(fuente, "lighthouse-result", "E", "V"))
        self.assertEqual(len(salida.resultados), 1)
        self.assertEqual(salida.contexto_adicional["rendimientoCompuesto"]["valorOriginal"], 0.93)
        self.assertEqual(salida.contexto_adicional["rendimientoCompuesto"]["valorContextual"], 93)
        self.assertFalse(any(r.origen.id_indicador == "P-06" for r in salida.resultados))

    def test_detecta_alteraciones_de_hash_fragmento_mapeo_contexto_y_version(self):
        cambios = (
            lambda l: setattr(l, "sha256_original", "0" * 64),
            lambda l: setattr(l.resultados[0], "valor_original", 1),
            lambda l: setattr(l.resultados[0], "id_indicador", "P-01"),
            lambda l: l.contexto["configSettings"].update(formFactor="desktop"),
            lambda l: l.entrada_original["audits"].clear(),
            lambda l: setattr(l, "version_catalogo_mapeos", "otra-version"),
        )
        for indice, cambiar in enumerate(cambios):
            with self.subTest(cambio=indice):
                lote = lote_metrica()
                cambiar(lote)
                with self.assertRaises(ErrorProcesamiento):
                    clasificar_lote(lote)

    def test_hash_del_archivo_intermedio_y_hash_original_son_distintos(self):
        ruta = RAIZ / "datos/muestras_publicas/lighthouse_importado.json"
        salida = clasificar_archivo(ruta)
        self.assertEqual(salida.sha256_lote_importado, hashlib.sha256(ruta.read_bytes()).hexdigest())
        self.assertEqual(salida.tipo_hash_entrada, "archivo")
        self.assertNotEqual(salida.sha256_lote_importado, salida.entrada_importada.sha256_original)
        with self.assertRaises(ErrorProcesamiento):
            clasificar_lote(lote_metrica(), archivo_intermedio=ruta.read_bytes())

    def test_json_corrupto_no_finito_y_claves_repetidas_rechazados(self):
        for texto in ("{", '{"a":NaN}', '{"a":1e999}', '{"a":1,"a":2}'):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                json_estricto(texto)

    def test_mismas_entradas_mismas_decisiones_sin_mutacion(self):
        lote = lote_axe("incomplete")
        antes = lote.model_dump_json()
        a, b = clasificar_lote(lote), clasificar_lote(lote)
        self.assertEqual(a.resultados, b.resultados)
        self.assertEqual(a.sha256_reglas, b.sha256_reglas)
        self.assertEqual(lote.model_dump_json(), antes)

    def test_muestras_publicas_contra_tabla_de_expectativas_separada(self):
        expectativas = ejemplo("clasificacion_esperada_muestras_publicas_v1.json")["muestras"]
        for nombre, filas in expectativas.items():
            with self.subTest(muestra=nombre):
                ruta = RAIZ / "datos/muestras_publicas" / f"{nombre}_importado.json"
                antes = ruta.read_bytes()
                salida = clasificar_archivo(ruta)
                observado = [{"id": r.origen.identificador_origen, "grupo": r.origen.estado_original,
                              "estado": r.decision.estado_normalizado, "prioridad": r.decision.prioridad}
                             for r in salida.resultados]
                self.assertEqual(observado, filas)
                self.assertEqual(ruta.read_bytes(), antes)
                self.assertEqual(salida.historial_revisiones, [])
                if nombre == "axe":
                    self.assertEqual(len(salida.fuentes_fuera_cobertura), 82)
                    self.assertEqual(len({r.origen.id_resultado for r in salida.resultados}), 13)

    def test_cli_clasificar_crea_archivo_y_no_sobrescribe_ni_modifica_fuentes(self):
        ruta = RAIZ / "datos/muestras_publicas/lighthouse_importado.json"
        antes = ruta.read_bytes()
        with tempfile.TemporaryDirectory() as temporal:
            salida = Path(temporal) / "clasificado.json"
            args = ["clasificar", str(ruta), "--salida", str(salida)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)
            creado = salida.read_bytes()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 1)
                self.assertEqual(main(["clasificar", str(ruta), "--salida", str(ruta)]), 1)
            self.assertEqual(salida.read_bytes(), creado)
            self.assertEqual(ruta.read_bytes(), antes)

    def test_cli_archivo_invalido_no_crea_salida(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta, salida = Path(temporal) / "mal.json", Path(temporal) / "salida.json"
            for contenido in ('{"versionEsquema":"0.2.0"}', '{'):
                ruta.write_text(contenido, encoding="utf-8")
                with redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(main(["clasificar", str(ruta), "--salida", str(salida)]), 1)
                self.assertIn("ERROR:FORMATO", error.getvalue())
                self.assertFalse(salida.exists())


if __name__ == "__main__":
    unittest.main()
