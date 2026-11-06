"""Regresiones de H-01 a H-07 y reglas de comparación/prioridad de la auditoría."""

import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tests import test_integracion as escenarios
from modelo_calidad_web.importacion import importar_datos
from modelo_calidad_web.integracion import generar_informe
from modelo_calidad_web.main import main
from modelo_calidad_web.procesamiento import clasificar_archivo, clasificar_lote, registrar_revision_archivo
from modelo_calidad_web.procesamiento.revision import comprobar_hash_intermedio, validar_lote_procesado
from modelo_calidad_web.validacion.catalogos import cargar_catalogos, ErrorCatalogo

ROOT = Path(__file__).resolve().parents[1]


class CorreccionesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        escenarios.IntegracionTest.setUpClass()

    @classmethod
    def tearDownClass(cls):
        escenarios.IntegracionTest.tearDownClass()

    def setUp(self):
        self.s = escenarios.IntegracionTest()
        self.s.setUp()
        self.addCleanup(self.s.doCleanups)

    def comparacion(self):
        grupos = [v["grupos"][0] for v in self.s.manifiesto["vistas"]]
        c = {"idComparacion": "C-SIMULADA", "grupos": [g["idGrupo"] for g in grupos],
             "protocolo": "SIMULADO: condiciones iguales y configuraciones observadas compatibles.",
             "responsable": "REVISOR SIMULADO", "fechaHora": "2026-11-04T11:00:00-05:00",
             "condicionesComunes": copy.deepcopy(grupos[0]["condicionesDeclaradas"]),
             "maxDiferenciaSegundos": 3600}
        self.s.manifiesto["comparaciones"] = [c]
        return c

    def dos_nodos(self):
        def modificar(a):
            r = a["incomplete"][0]
            r["nodes"].append({**r["nodes"][0], "target": ["#sin-revisar"]})
        self.s.reconstruir("axe", modificar)
        f = self.s.fuente()
        ruta = self.s.base / f["ruta"]
        r = next(r for r in escenarios.leer(ruta)["resultados"]
                 if r["origen"]["identificadorOrigen"] == "link-name")
        registro = {"idResultado": r["origen"]["idResultado"],
                    "responsable": "REVISOR SIMULADO", "fechaHora": "2026-11-04T11:00:00-05:00",
                    "estadoRevisado": "favorable", "fundamento": "SIMULADO", "evidencia": "SIMULADA"}
        return ruta, registro

    def revisar(self, ruta, registro):
        self.s.guardar(self.s.base / "registro.json", registro)
        lote = registrar_revision_archivo(ruta, self.s.base / "registro.json")
        self.s.actualizar_fuente("axe", lote.model_dump(mode="json", by_alias=True))
        return lote

    def test_mismo_json_reformateado_no_infla_conteos(self):
        f = self.s.fuente("wave")
        original = escenarios.leer(self.s.base / f["ruta"])["entradaImportada"]
        compacto = json.dumps(original["entradaOriginal"], sort_keys=True, separators=(",", ":"))
        lote = clasificar_lote(importar_datos(
            original["entradaOriginal"], original["formatoFuente"], original["idEvaluacion"],
            original["idModuloVista"], texto_original=compacto, perfil="incremento-3"))
        ruta = self.s.base / "copia.json"
        self.s.guardar(ruta, lote.model_dump(mode="json", by_alias=True))
        self.s.grupo["fuentes"].append({"idFuente": "COPIA", "ruta": ruta.name,
                                       "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest()})
        self.s.esperar_error("FUENTE_REPETIDA")

    def test_capturas_independientes_con_fecha_distinta_no_se_confunden(self):
        f = self.s.fuente("lighthouse")
        raw = escenarios.leer(self.s.base / f["ruta"])["entradaImportada"]["entradaOriginal"]
        raw["fetchTime"] = "2026-11-04T10:03:00-05:00"
        lote = clasificar_lote(importar_datos(raw, "lighthouse-result", self.s.grupo["idEvaluacion"],
                                             "VISTA-inicio", perfil="incremento-3"))
        ruta = self.s.base / "segunda.json"
        self.s.guardar(ruta, lote.model_dump(mode="json", by_alias=True))
        self.s.grupo["fuentes"].append({"idFuente": "SEGUNDA", "ruta": ruta.name,
                                       "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest()})
        d = self.s.ejecutar()
        i = next(i for dim in d.vistas[0].grupos[0].dimensiones for i in dim.indicadores
                 if i.id_indicador == "P-02")
        self.assertEqual(len(i.metricas), 2)  # No se elige una captura ni se promedia.

    def test_ancho_y_alto_lighthouse_incompatibles_se_rechazan(self):
        self.s.reconstruir("lighthouse", lambda l: l["configSettings"]["screenEmulation"].update(
            width=1280, height=800))
        self.s.esperar_error("CONTEXTO_INCOMPATIBLE")

    def test_ventanas_observadas_se_contrastan_aunque_no_estan_declaradas(self):
        self.s.grupo["condicionesDeclaradas"] = {"navegador": "SIMULADO"}
        self.s.reconstruir("lighthouse", lambda l: l["configSettings"]["screenEmulation"].update(
            width=1280, height=800))
        self.s.esperar_error("CONTEXTO_INCOMPATIBLE")

    def test_revisar_un_nodo_mantiene_pendiente_el_otro(self):
        ruta, registro = self.dos_nodos()
        lote = self.revisar(ruta, {**registro, "alcance": "nodo", "indiceNodo": 0})
        d = self.s.ejecutar()
        obs = [o for o in d.vistas[0].grupos[0].observaciones
               if o.referencia.id_resultado == registro["idResultado"]]
        self.assertEqual([o.estado_vigente for o in obs], ["favorable", "requiere_revision"])
        self.assertEqual([o.pendiente_revision for o in obs], [False, True])
        self.assertEqual(obs[1].estado_automatico, "requiere_revision")
        self.assertEqual(len(lote.historial_revisiones), 1)

    def test_multinodo_sin_alcance_explicito_se_rechaza(self):
        ruta, registro = self.dos_nodos()
        self.s.guardar(self.s.base / "registro.json", registro)
        with self.assertRaisesRegex(ValueError, "alcance"):
            registrar_revision_archivo(ruta, self.s.base / "registro.json")

    def test_resultado_completo_requiere_declaracion_y_cubre_ambos_nodos(self):
        ruta, registro = self.dos_nodos()
        self.revisar(ruta, {**registro, "alcance": "resultado_completo"})
        obs = [o for o in self.s.ejecutar().vistas[0].grupos[0].observaciones
               if o.referencia.id_resultado == registro["idResultado"]]
        self.assertEqual([o.estado_vigente for o in obs], ["favorable", "favorable"])

    def test_revisiones_por_nodo_conservan_historial_y_no_se_sustituyen(self):
        ruta, registro = self.dos_nodos()
        self.revisar(ruta, {**registro, "alcance": "nodo", "indiceNodo": 0})
        self.revisar(ruta, {**registro, "alcance": "nodo", "indiceNodo": 1,
                            "estadoRevisado": "desfavorable", "fechaHora": "2026-11-04T12:00:00-05:00"})
        obs = [o for o in self.s.ejecutar().vistas[0].grupos[0].observaciones
               if o.referencia.id_resultado == registro["idResultado"]]
        self.assertEqual([o.estado_vigente for o in obs], ["favorable", "desfavorable"])
        self.assertEqual([o.revision_vigente.numero for o in obs], [1, 2])

    def test_alcance_e_indice_incoherentes_o_booleanos_se_rechazan(self):
        ruta, registro = self.dos_nodos()
        for campos in ({"alcance": "nodo"}, {"indiceNodo": 0}, {"alcance": "resultado_completo", "indiceNodo": 0},
                       {"alcance": "nodo", "indiceNodo": True}, {"alcance": "nodo", "indiceNodo": 99}):
            self.s.guardar(self.s.base / "registro.json", {**registro, **campos})
            with self.subTest(campos=campos), self.assertRaises(ValueError):
                registrar_revision_archivo(ruta, self.s.base / "registro.json")

    def test_revision_anterior_a_captura_se_rechaza(self):
        ruta, registro = self.dos_nodos()
        self.s.guardar(self.s.base / "registro.json", {
            **registro, "fechaHora": "1900-01-01T10:00:00-05:00", "alcance": "resultado_completo"})
        with self.assertRaisesRegex(ValueError, "captura"):
            registrar_revision_archivo(ruta, self.s.base / "registro.json")

    def test_hash_intermedio_representacion_alterada_no_se_acepta(self):
        f = self.s.fuente()
        datos = escenarios.leer(self.s.base / f["ruta"])
        datos["sha256LoteImportado"] = "0" * 64
        self.s.actualizar_fuente("axe", datos)
        self.s.esperar_error("INTEGRIDAD")

    def test_archivo_intermedio_exacto_se_conserva_y_verifica(self):
        ruta = ROOT / "datos/muestras_publicas/axe_importado.json"
        lote = clasificar_archivo(ruta)
        self.assertEqual(lote.texto_lote_importado.encode("utf-8"), ruta.read_bytes())
        self.assertEqual(comprobar_hash_intermedio(lote), "comprobado")
        lote.sha256_lote_importado = "0" * 64
        with self.assertRaises(ValueError):
            validar_lote_procesado(lote)

    def test_archivo_intermedio_historico_ausente_queda_no_comprobado(self):
        lote = clasificar_archivo(ROOT / "datos/muestras_publicas/axe_importado.json")
        lote.texto_lote_importado = None
        self.assertEqual(comprobar_hash_intermedio(lote), "no_comprobado_archivo_historico_ausente")
        validar_lote_procesado(lote)  # La decisión se verifica, no se inventa el archivo perdido.

    def test_texto_intermedio_incoherente_aunque_hash_coincida_se_rechaza(self):
        lote = clasificar_archivo(ROOT / "datos/muestras_publicas/axe_importado.json")
        datos = json.loads(lote.texto_lote_importado)
        datos["idEvaluacion"] = "OTRA"
        lote.texto_lote_importado = json.dumps(datos)
        lote.sha256_lote_importado = hashlib.sha256(lote.texto_lote_importado.encode()).hexdigest()
        with self.assertRaises(ValueError):
            validar_lote_procesado(lote)

    def test_validar_rechaza_claves_duplicadas_no_finitos_y_fecha_sin_zona(self):
        datos = escenarios.leer(ROOT / "datos/ejemplos/wave_ejemplo.json")
        textos = ['{"idIndicador":"A-99",' + json.dumps(datos)[1:],
                  json.dumps({**datos, "fechaHora": "2026-11-04T10:00:00"}),
                  json.dumps({**datos, "datosOriginales": {"valor": float("nan")}})]
        ruta = self.s.base / "invalido.json"
        for texto in textos:
            ruta.write_text(texto, encoding="utf-8")
            with self.subTest(texto=texto), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["validar", str(ruta)]), 1)

    def catalogos(self, archivo, transform):
        carpeta = self.s.base / archivo.replace(".json", "")
        carpeta.mkdir()
        for p in (ROOT / "src/modelo_calidad_web/catalogos").glob("*.json"):
            (carpeta / p.name).write_bytes(p.read_bytes())
        ruta = carpeta / archivo
        datos = escenarios.leer(ruta)
        transform(datos)
        self.s.guardar(ruta, datos)
        return carpeta

    def test_catalogos_rechazan_identificadores_repetidos(self):
        for nombre in ("indicadores.json", "dimensiones.json", "estados.json", "prioridades.json",
                       "reglas_normalizacion.json"):
            carpeta = self.catalogos(nombre, lambda filas: filas.append(copy.deepcopy(filas[0])))
            with self.subTest(archivo=nombre), self.assertRaises(ErrorCatalogo):
                cargar_catalogos(carpeta)

    def test_catalogos_rechazan_campos_ausentes_y_referencia_de_dimension_inexistente(self):
        carpeta = self.catalogos("indicadores.json", lambda f: f[0].update(dimension="D-INEXISTENTE"))
        with self.assertRaises(ErrorCatalogo):
            cargar_catalogos(carpeta)
        carpeta = self.catalogos("dimensiones.json", lambda f: f[0].pop("nombre"))
        with self.assertRaises(ErrorCatalogo):
            cargar_catalogos(carpeta)

    def test_comparacion_sin_protocolo_no_se_infiere(self):
        d = self.s.ejecutar()
        self.assertEqual(d.comparaciones, [])
        self.assertTrue(all(r.vistas_con_misma_comprobacion == 1 for r in d.recomendaciones))

    def test_comparacion_explicita_muestra_diferencia_lcp_sin_nota_global(self):
        self.comparacion()
        d = self.s.ejecutar()
        lcp = next(m for m in d.comparaciones[0]["metricas"] if m["idIndicador"] == "P-02")
        self.assertEqual(lcp["situacion"], "comparable")
        self.assertEqual([f["diferenciaRespectoPrimerGrupo"] for f in lcp["filas"]], [0, 1300])
        self.assertFalse(hasattr(d, "puntaje_global"))
        self.assertEqual(d.comparaciones[0]["coberturaPorGrupo"][0]["idGrupo"], "GRUPO-inicio")

    def test_comparacion_requiere_condiciones_suficientes_y_fecha_con_zona(self):
        c = self.comparacion()
        del c["condicionesComunes"]["red"]
        self.s.esperar_error("FORMATO")

    def test_comparacion_no_admite_fecha_sin_zona_dimension_booleana_o_grupos_repetidos(self):
        for cambio in (lambda c: c.update(fechaHora="2026-11-04T11:00:00"),
                       lambda c: c["condicionesComunes"].update(ventanaAncho=True),
                       lambda c: c.update(grupos=["GRUPO-inicio", "GRUPO-inicio"])):
            c = self.comparacion()
            cambio(c)
            with self.subTest(c=c):
                self.s.esperar_error("FORMATO")

    def test_comparacion_no_admite_dos_grupos_de_una_vista(self):
        c = self.comparacion()
        otro = self.s.manifiesto["vistas"].pop()["grupos"][0]
        self.s.manifiesto["vistas"][0]["grupos"].append(otro)
        # No se llega a comparar porque las fuentes pertenecen a otra vista.
        self.s.esperar_error("CONTEXTO_INCOMPATIBLE")

    def test_comparacion_rechaza_condiciones_dispares(self):
        self.comparacion()
        self.s.manifiesto["vistas"][1]["grupos"][0]["condicionesDeclaradas"]["cpu"] = "OTRA"
        self.s.esperar_error("COMPARACION_INVALIDA")

    def test_comparacion_rechaza_grupo_inexistente_o_de_la_misma_vista(self):
        c = self.comparacion()
        c["grupos"][1] = "INEXISTENTE"
        self.s.esperar_error("COMPARACION_INVALIDA")

    def test_comparacion_rechaza_intervalo_excesivo_y_fecha_temprana(self):
        c = self.comparacion()
        c["maxDiferenciaSegundos"] = 1
        self.s.esperar_error("COMPARACION_INVALIDA")
        c["maxDiferenciaSegundos"] = 3600
        c["fechaHora"] = "1900-01-01T00:00:00-05:00"
        self.s.esperar_error("COMPARACION_INVALIDA")

    def test_versiones_de_herramienta_diferentes_no_son_comparables(self):
        self.comparacion()
        self.s.reconstruir("axe", lambda a: a["testEngine"].update(version="OTRA"), vista=1)
        self.s.esperar_error("COMPARACION_INVALIDA")

    def test_configuracion_lighthouse_distinta_no_produce_diferencia_numerica(self):
        self.comparacion()
        self.s.reconstruir("lighthouse", lambda l: l["configSettings"].update(
            throttling={"cpuSlowdownMultiplier": 8}), vista=1)
        d = self.s.ejecutar()
        for m in d.comparaciones[0]["metricas"]:
            self.assertEqual(m["situacion"], "no_comparable")
            self.assertTrue(all("diferenciaRespectoPrimerGrupo" not in f for f in m["filas"]))

    def test_varias_mediciones_no_se_resumen_en_una_para_comparar(self):
        self.test_capturas_independientes_con_fecha_distinta_no_se_confunden()
        self.comparacion()
        lcp = next(m for m in self.s.ejecutar().comparaciones[0]["metricas"] if m["idIndicador"] == "P-02")
        self.assertEqual(lcp["motivo"], "sin_medicion_unica_por_grupo")
        self.assertEqual(len(lcp["filas"][0]["mediciones"]), 2)

    def test_metrica_ausente_no_se_inventa_para_comparar(self):
        self.comparacion()
        def cambiar(l):
            l["categories"]["performance"]["auditRefs"] = [
                r for r in l["categories"]["performance"]["auditRefs"] if r["id"] != "largest-contentful-paint"]
        self.s.reconstruir("lighthouse", cambiar, vista=1)
        lcp = next(m for m in self.s.ejecutar().comparaciones[0]["metricas"] if m["idIndicador"] == "P-02")
        self.assertEqual(lcp["motivo"], "sin_medicion_unica_por_grupo")
        self.assertEqual(lcp["filas"][1]["mediciones"], [])

    def test_repeticion_cuenta_comprobaciones_no_puntaje_ni_causas(self):
        self.comparacion()
        d = self.s.ejecutar()
        alt = [r for r in d.recomendaciones if r.id_indicador == "A-01" and r.tipo == "correccion_a_verificar"]
        self.assertTrue(all(r.vistas_con_misma_comprobacion == 2 for r in alt))
        self.assertTrue(all("no demuestra identidad de causa" in r.criterio_desempate for r in alt))

    def test_cantidad_elementos_no_suma_dos_evidencias_del_mismo_elemento(self):
        d = self.s.ejecutar()
        rec = next(r for r in d.recomendaciones if r.id_indicador == "A-01"
                   and r.tipo == "correccion_a_verificar" and r.id_modulo_vista == "VISTA-inicio")
        self.assertEqual(rec.elementos_afectados_minimos, 2)
        self.assertEqual(rec.elementos_observados_maximos, 2)  # Tres evidencias, dos elementos.

    def test_equivalencia_incierta_se_expresa_como_rango_no_conteo_falso(self):
        self.s.grupo["coincidencias"] = []
        d = self.s.ejecutar()
        rec = next(r for r in d.recomendaciones if r.id_indicador == "A-01"
                   and r.tipo == "correccion_a_verificar" and r.id_modulo_vista == "VISTA-inicio")
        self.assertEqual((rec.elementos_afectados_minimos, rec.elementos_observados_maximos), (2, 3))

    def test_desempate_toma_cantidad_y_revisiones_asociadas(self):
        self.comparacion()
        d = self.s.ejecutar()
        altas = [r for r in d.recomendaciones if r.orden_tecnico == 1]
        self.assertTrue(all(r.id_indicador == "A-01" for r in altas[:4]))
        self.assertTrue(all(r.casos_revision_asociados == 1 for r in altas[:4]))

    def test_diagnostico_historico_exige_regenerar_sin_sobrescribirlo(self):
        historico = ROOT / "docs/evidencias_incremento_4_2026_11_04/demostracion_final/diagnostico.json"
        antes = historico.read_bytes()
        with self.assertRaisesRegex(ValueError, "histórico"):
            generar_informe(historico)
        self.assertEqual(historico.read_bytes(), antes)

    def test_informe_muestra_comparacion_rango_elementos_y_hash_intermedio(self):
        self.comparacion()
        ruta, d = self.s.guardar_diagnostico()
        informe = generar_informe(ruta)
        for cadena in ("Comparaciones entre vistas", "1300", "mínimo identificado",
                       "Verificación de la huella intermedia", "comprobado"):
            self.assertIn(cadena, informe)
        self.assertEqual(d.version_integrador, "0.4.1")

    def test_alcance_explicito_de_los_veinte_indicadores_no_amplia_cobertura(self):
        d = self.s.ejecutar()
        indicadores = {i.id_indicador: i for dim in d.vistas[0].grupos[0].dimensiones
                       for i in dim.indicadores}
        self.assertEqual(len(indicadores), 20)
        self.assertIn("no acredita operabilidad completa", indicadores["A-09"].limitacion)
        self.assertIn("no cubre todos los controles", indicadores["A-03"].limitacion)
        self.assertEqual(indicadores["P-06"].ids_hallazgos, [])
        self.assertEqual(len(d.sha256_catalogo_alcance), 64)

    def test_alterar_etiqueta_de_hash_o_comparacion_no_pasa_por_recalculo(self):
        self.comparacion()
        ruta, _ = self.s.guardar_diagnostico()
        original = escenarios.leer(ruta)
        for cambiar in (lambda d: d["fuentes"][0].update(verificacionHashIntermedio="inventado"),
                        lambda d: d["comparaciones"][0]["metricas"][0]["filas"][0].update(
                            diferenciaRespectoPrimerGrupo=12345)):
            datos = copy.deepcopy(original)
            cambiar(datos)
            self.s.guardar(ruta, datos)
            with self.assertRaisesRegex(ValueError, "alterados"):
                generar_informe(ruta)


if __name__ == "__main__":
    unittest.main()

