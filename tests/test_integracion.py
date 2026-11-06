"""Casos controlados del cuarto incremento; no son datos del Portal Académico."""

import copy
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ))

from modelo_calidad_web.importacion import importar_datos
from modelo_calidad_web.integracion import diagnosticar_archivo, generar_informe, verificar_diagnostico_archivo
from modelo_calidad_web.main import main
from modelo_calidad_web.procesamiento import ErrorProcesamiento, clasificar_lote, registrar_revision_archivo
from scripts.preparar_ejemplo_incremento_4 import preparar


def leer(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


class IntegracionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporal_base = tempfile.TemporaryDirectory()
        cls.carpeta_base = Path(cls.temporal_base.name) / "datos"
        preparar(cls.carpeta_base)

    @classmethod
    def tearDownClass(cls):
        cls.temporal_base.cleanup()

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.base = Path(self.temporal.name) / "ejemplo"
        shutil.copytree(self.carpeta_base, self.base)
        self.ruta = self.base / "manifiesto.json"
        self.manifiesto = leer(self.ruta)
        self.grupo = self.manifiesto["vistas"][0]["grupos"][0]

    def guardar(self, ruta, datos):
        Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def ejecutar(self):
        self.guardar(self.ruta, self.manifiesto)
        return diagnosticar_archivo(self.ruta)

    def fuente(self, etiqueta="axe", vista=0):
        return next(f for f in self.manifiesto["vistas"][vista]["grupos"][0]["fuentes"]
                    if f["idFuente"].endswith("-" + etiqueta))

    def actualizar_fuente(self, etiqueta, datos, vista=0):
        declarada = self.fuente(etiqueta, vista)
        self.guardar(self.base / declarada["ruta"], datos)
        declarada["sha256"] = hashlib.sha256((self.base / declarada["ruta"]).read_bytes()).hexdigest()

    def reconstruir(self, etiqueta, cambio, vista=0):
        declarada = self.fuente(etiqueta, vista)
        lote = leer(self.base / declarada["ruta"])
        entrada = lote["entradaImportada"]
        fuente = entrada["entradaOriginal"]
        cambio(fuente)
        importado = importar_datos(fuente, entrada["formatoFuente"], entrada["idEvaluacion"],
                                  entrada["idModuloVista"], perfil="incremento-3",
                                  ejecutor="playwright" if etiqueta == "axe" else None)
        procesado = clasificar_lote(importado)
        self.actualizar_fuente(etiqueta, procesado.model_dump(mode="json", by_alias=True), vista)

    def esperar_error(self, codigo):
        with self.assertRaises(ErrorProcesamiento) as error:
            self.ejecutar()
        self.assertEqual(error.exception.codigo, codigo)

    def guardar_diagnostico(self):
        ruta = self.base / "diagnostico.json"
        diagnostico = self.ejecutar()
        ruta.write_text(diagnostico.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
        return ruta, diagnostico

    def test_dos_vistas_tres_dimensiones_y_conteos_de_referencia(self):
        esperado = leer(RAIZ / "datos/ejemplos/incremento_4/esperado.json")
        d = self.ejecutar()
        self.assertEqual(len(d.vistas), 2)
        for vista, nombre in zip(d.vistas, ("inicio", "cursos")):
            g = vista.grupos[0]
            self.assertEqual([dim.id_dimension for dim in g.dimensiones], ["D-AC", "D-RE", "D-US"])
            self.assertEqual(len(g.observaciones), esperado["porVista"]["observaciones"])
            self.assertEqual(sum(len(f.lote.resultados) for f in d.fuentes
                                 if f.id_fuente.startswith(nombre)), esperado["porVista"]["resultadosFuente"])
            self.assertEqual(len(g.hallazgos), esperado[nombre]["hallazgos"])
            self.assertEqual(len([r for r in d.recomendaciones if r.id_modulo_vista == vista.id_modulo_vista]),
                             esperado[nombre]["recomendaciones"])
            lcp = next(i for dim in g.dimensiones for i in dim.indicadores if i.id_indicador == "P-02")
            self.assertEqual(lcp.metricas[0]["valorNormalizado"], esperado[nombre]["LCP"]["valor"])
            self.assertEqual(lcp.metricas[0]["estado"], esperado[nombre]["LCP"]["estado"])

    def test_coincidencia_conserva_ambos_origenes_y_otro_nodo_separado(self):
        g = self.ejecutar().vistas[0].grupos[0]
        alt = [h for h in g.hallazgos if h.id_indicador == "A-01" and h.estado == "desfavorable"]
        self.assertEqual(len(alt), 2)
        consolidado = next(h for h in alt if h.id_coincidencia)
        self.assertEqual(len(consolidado.ids_observaciones), 2)
        otro = next(h for h in alt if h.id_coincidencia is None)
        observacion = next(o for o in g.observaciones if o.id_observacion == otro.ids_observaciones[0])
        self.assertEqual(observacion.ubicacion, ["#otra-imagen"])
        self.assertEqual(observacion.referencia.indice_nodo, 1)

    def test_sin_confirmacion_no_fusiona_selectores_iguales(self):
        self.grupo["coincidencias"] = []
        g = self.ejecutar().vistas[0].grupos[0]
        self.assertEqual(len([h for h in g.hallazgos if h.id_indicador == "A-01"
                              and h.estado == "desfavorable"]), 3)
        self.assertEqual(len([h for h in g.hallazgos if h.id_indicador == "A-04"]), 2)

    def test_xpath_y_css_distintos_solo_se_fusionan_con_registro(self):
        def cambio(wave):
            next(r for r in wave["resultados"] if r["identificador"] == "alt_missing")["ubicacion"] = "/HTML/BODY/IMG[1]"
        self.reconstruir("wave", cambio)
        g = self.ejecutar().vistas[0].grupos[0]
        self.assertEqual(len([h for h in g.hallazgos if h.id_coincidencia]), 1)

    def test_coincidencia_requiere_documentacion_y_zona(self):
        for campo in ("responsable", "fundamento", "evidencia", "problemaComun", "elementoCanonico"):
            original = copy.deepcopy(self.grupo["coincidencias"][0])
            del self.grupo["coincidencias"][0][campo]
            with self.subTest(campo=campo):
                self.esperar_error("FORMATO")
            self.grupo["coincidencias"][0] = original
        self.grupo["coincidencias"][0]["fechaHora"] = "2026-11-04T10:06:00"
        self.esperar_error("FORMATO")

    def test_coincidencia_rechaza_nodo_booleano_o_inexistente(self):
        ref = self.grupo["coincidencias"][0]["referencias"][1]
        for indice, codigo in ((True, "FORMATO"), (900, "COINCIDENCIA_INVALIDA"), (None, "COINCIDENCIA_INVALIDA")):
            ref["indiceNodo"] = indice
            with self.subTest(indice=indice):
                self.esperar_error(codigo)

    def test_observacion_no_se_reutiliza_en_dos_coincidencias(self):
        otra = copy.deepcopy(self.grupo["coincidencias"][0])
        otra["idCoincidencia"] = "OTRA"
        self.grupo["coincidencias"].append(otra)
        self.esperar_error("COINCIDENCIA_INVALIDA")

    def test_no_fusiona_indicadores_distintos_o_una_sola_herramienta(self):
        ref = self.grupo["coincidencias"][0]["referencias"][0]
        wave = leer(self.base / self.fuente("wave")["ruta"])
        ref["idResultado"] = next(r["origen"]["idResultado"] for r in wave["resultados"]
                                  if r["origen"]["idIndicador"] == "A-04")
        self.esperar_error("COINCIDENCIA_INVALIDA")
        axe_ref = self.grupo["coincidencias"][0]["referencias"][1]
        self.grupo["coincidencias"][0]["referencias"][0] = {**axe_ref, "indiceNodo": 1}
        self.esperar_error("COINCIDENCIA_INVALIDA")

    def test_no_fusiona_incertidumbre(self):
        self.reconstruir("axe", lambda a: a["incomplete"].append(a["violations"].pop(0)))
        # Actualizar ID porque el grupo fuente cambió a incomplete.
        datos = leer(self.base / self.fuente("axe")["ruta"])
        ref = self.grupo["coincidencias"][0]["referencias"][1]
        ref["idResultado"] = next(r["origen"]["idResultado"] for r in datos["resultados"]
                                  if r["origen"]["identificadorOrigen"] == "image-alt")
        self.esperar_error("COINCIDENCIA_INVALIDA")

    def test_coincidencia_de_otro_grupo_se_rechaza(self):
        self.grupo["coincidencias"][0]["referencias"][1]["idFuente"] = "cursos-axe"
        self.esperar_error("COINCIDENCIA_INVALIDA")

    def test_identificadores_de_vista_grupo_y_fuente_no_se_repiten(self):
        segundo = self.manifiesto["vistas"][1]
        for campo, objeto, valor in (
            ("idModuloVista", segundo, self.manifiesto["vistas"][0]["idModuloVista"]),
            ("idGrupo", segundo["grupos"][0], self.grupo["idGrupo"]),
            ("idFuente", segundo["grupos"][0]["fuentes"][0], self.grupo["fuentes"][0]["idFuente"]),
        ):
            antes = objeto[campo]
            objeto[campo] = valor
            with self.subTest(campo=campo):
                self.esperar_error("FORMATO")
            objeto[campo] = antes

    def test_fuente_ajena_a_url_evaluacion_o_vista_se_rechaza(self):
        vista = self.manifiesto["vistas"][0]
        for campo, objeto, valor in (
            ("url", vista, vista["url"] + "?otra=true"),
            ("idEvaluacion", self.grupo, "OTRA"),
            ("idModuloVista", vista, "OTRA"),
        ):
            antes = objeto[campo]
            objeto[campo] = valor
            with self.subTest(campo=campo):
                self.esperar_error("CONTEXTO_INCOMPATIBLE")
            objeto[campo] = antes

    def test_captura_fuera_intervalo_o_fechas_sin_zona_se_rechazan(self):
        self.grupo["inicio"] = "2026-11-04T10:03:00-05:00"
        self.esperar_error("CONTEXTO_INCOMPATIBLE")
        self.grupo["inicio"] = "2026-11-04T10:03:00"
        self.esperar_error("FORMATO")

    def test_perfiles_y_ventana_incompatibles_se_rechazan(self):
        for campo, valor in (("perfilRendimiento", "desktop"), ("perfilAcceso", "estudiante")):
            anterior = self.grupo[campo]
            self.grupo[campo] = valor
            with self.subTest(campo=campo):
                self.esperar_error("CONTEXTO_INCOMPATIBLE")
            self.grupo[campo] = anterior
        self.grupo["condicionesDeclaradas"]["ventanaAncho"] = 1280
        self.esperar_error("CONTEXTO_INCOMPATIBLE")

    def test_perfil_ausente_no_recibe_juicio_favorable_de_tiempos(self):
        self.grupo["perfilRendimiento"] = None
        self.grupo["coincidencias"] = []
        self.grupo["fuentes"] = [self.fuente("lighthouse")]
        self.reconstruir("lighthouse", lambda l: l["configSettings"].pop("formFactor"))
        g = self.ejecutar().vistas[0].grupos[0]
        por_id = {o.id_indicador: o.estado_vigente for o in g.observaciones}
        self.assertEqual(por_id["P-01"], "no_evaluado")
        self.assertEqual(por_id["P-04"], "favorable")

    def test_fuente_repetida_no_infla_conteos_aunque_cambien_ids_del_lote(self):
        entrada = leer(self.base / self.fuente("wave")["ruta"])["entradaImportada"]
        segundo = self.manifiesto["vistas"][1]
        segundo["url"] = self.manifiesto["vistas"][0]["url"]
        lote = clasificar_lote(importar_datos(
            entrada["entradaOriginal"], entrada["formatoFuente"], "EVAL-SIMULADA-cursos",
            "VISTA-cursos", perfil="incremento-3", texto_original=entrada["textoOriginal"]))
        self.actualizar_fuente("wave", lote.model_dump(mode="json", by_alias=True), vista=1)
        self.esperar_error("FUENTE_REPETIDA")

    def test_hash_incorrecto_y_decision_alterada_no_se_aceptan(self):
        ref = self.fuente()
        original = ref["sha256"]
        ref["sha256"] = "0" * 64
        self.esperar_error("INTEGRIDAD")
        ref["sha256"] = original
        datos = leer(self.base / ref["ruta"])
        datos["resultados"][0]["decision"]["estadoNormalizado"] = "favorable"
        self.actualizar_fuente("axe", datos)
        self.esperar_error("INTEGRIDAD")

    def test_cobertura_fuera_catalogo_y_contexto_alterados_se_rechazan(self):
        ref = self.fuente()
        original = leer(self.base / ref["ruta"])
        for campo, valor in (("coberturaIndicadores", []), ("fuentesFueraCobertura", [
            {"identificadorOrigen": "inventado", "rutaOrigen": "/x", "motivo": "fuera_catalogo_admitido"}]),
                             ("contextoAdicional", {"falso": True})):
            datos = copy.deepcopy(original)
            datos[campo] = valor
            self.actualizar_fuente("axe", datos)
            with self.subTest(campo=campo):
                self.esperar_error("INTEGRIDAD")

    def test_revision_vigente_no_borra_automatica_y_cambia_solo_su_recomendacion(self):
        fuente = self.fuente()
        ruta = self.base / fuente["ruta"]
        datos = leer(ruta)
        resultado = next(r for r in datos["resultados"] if r["decision"]["revision"] == "pendiente")
        registro = {"idResultado": resultado["origen"]["idResultado"],
                    "responsable": "REVISOR SIMULADO", "fechaHora": "2026-11-04T11:00:00-05:00",
                    "estadoRevisado": "favorable", "fundamento": "Decisión simulada para probar historial.",
                    "evidencia": "EVIDENCIA SIMULADA"}
        ruta_registro = self.base / "revision.json"
        self.guardar(ruta_registro, registro)
        revisado = registrar_revision_archivo(ruta, ruta_registro)
        self.actualizar_fuente("axe", revisado.model_dump(mode="json", by_alias=True))
        d = self.ejecutar()
        o = next(o for o in d.vistas[0].grupos[0].observaciones
                 if o.referencia.id_resultado == registro["idResultado"])
        self.assertEqual(o.estado_automatico, "requiere_revision")
        self.assertEqual(o.estado_vigente, "favorable")
        self.assertIsNotNone(o.revision_vigente)
        self.assertFalse(o.pendiente_revision)
        self.assertFalse(any(o.id_observacion in r.ids_observaciones for r in d.recomendaciones))

    def test_revision_humana_no_fabrica_prioridad_tecnica(self):
        fuente = self.fuente()
        ruta = self.base / fuente["ruta"]
        datos = leer(ruta)
        resultado = next(r for r in datos["resultados"] if r["decision"]["revision"] == "pendiente")
        registro = {"idResultado": resultado["origen"]["idResultado"],
                    "responsable": "REVISOR SIMULADO", "fechaHora": "2026-11-04T11:00:00-05:00",
                    "estadoRevisado": "desfavorable", "fundamento": "Prueba simulada de decisión.",
                    "evidencia": "EVIDENCIA SIMULADA"}
        r = self.base / "revision.json"
        self.guardar(r, registro)
        revisado = registrar_revision_archivo(ruta, r)
        self.actualizar_fuente("axe", revisado.model_dump(mode="json", by_alias=True))
        d = self.ejecutar()
        rec = next(r for r in d.recomendaciones if r.id_indicador == "A-07" and r.id_modulo_vista == "VISTA-inicio")
        self.assertEqual(rec.prioridades_observadas, ["revision"])
        self.assertEqual(rec.orden_tecnico, 4)  # Fallo sin severidad técnica, no "alta".

    def test_historial_incoherente_no_se_integra(self):
        datos = leer(self.base / self.fuente()["ruta"])
        # Un registro aparentemente completo pero dirigido a un resultado inexistente.
        datos["historialRevisiones"] = [{
            "numero": 1, "situacion": "realizada", "sha256LotePrevio": "0" * 64,
            "registro": {"idResultado": "ajeno", "responsable": "SIMULADO",
                         "fechaHora": "2026-11-04T11:00:00-05:00", "estadoRevisado": "favorable",
                         "fundamento": "SIMULADO", "evidencia": "SIMULADO"},
            "decisionAutomatica": datos["resultados"][0]["decision"],
        }]
        self.actualizar_fuente("axe", datos)
        self.esperar_error("INTEGRIDAD")

    def test_ausencia_no_es_favorable_y_p06_sigue_contextual(self):
        g = self.ejecutar().vistas[0].grupos[0]
        indicadores = {i.id_indicador: i for dim in g.dimensiones for i in dim.indicadores}
        self.assertEqual(indicadores["U-01"].situacion, "sin_observaciones")
        self.assertTrue(all(n == 0 for n in indicadores["U-01"].estados_observados.values()))
        self.assertEqual(indicadores["P-06"].situacion, "contextual")
        self.assertEqual(indicadores["P-06"].contexto[0]["rendimientoCompuesto"]["valorContextual"], 72)
        self.assertEqual(indicadores["P-06"].ids_hallazgos, [])

    def test_vista_sin_fuentes_permanece_visible(self):
        self.manifiesto["vistas"].append({
            "idModuloVista": "SIN-DATOS", "nombre": "Vista pendiente", "url": "https://simulado.invalid/pendiente",
            "grupos": [],
        })
        d = self.ejecutar()
        self.assertEqual(d.vistas[-1].grupos, [])
        self.assertEqual(d.resumen_entre_vistas[-1]["dimensionesSinDatos"], ["D-AC", "D-RE", "D-US"])

    def test_recomendaciones_trazables_y_ordenadas_sin_prioridad_global(self):
        d = self.ejecutar()
        self.assertEqual([r.orden_tecnico for r in d.recomendaciones],
                         sorted(r.orden_tecnico for r in d.recomendaciones))
        for vista in d.vistas:
            for grupo in vista.grupos:
                hallazgos = {h.id_hallazgo: h for h in grupo.hallazgos}
                observaciones = {o.id_observacion for o in grupo.observaciones}
                for r in (r for r in d.recomendaciones if r.id_grupo == grupo.id_grupo):
                    self.assertEqual(r.ids_observaciones, hallazgos[r.id_hallazgo].ids_observaciones)
                    self.assertTrue(set(r.ids_observaciones) <= observaciones)
                    self.assertTrue(r.referencias)
        self.assertFalse(hasattr(d, "puntaje_global"))
        self.assertFalse(any(r.id_indicador == "P-06" for r in d.recomendaciones))
        revisiones = [r for r in d.recomendaciones if r.tipo == "revision"]
        self.assertTrue(all(r.accion.startswith("Revisar la evidencia") for r in revisiones))

    def test_texto_y_bytes_originales_intactos_y_diagnostico_autocontenido(self):
        antes = {f.name: f.read_bytes() for f in self.base.glob("*clasificado.json")}
        ruta, d = self.guardar_diagnostico()
        for f in d.fuentes:
            self.assertEqual(f.texto_original.encode("utf-8"), antes[f.ruta_declarada])
            self.assertTrue(f.texto_original.endswith("\n"))
        # Las rutas declaradas pueden no estar disponibles al leer el informe.
        for f in d.fuentes:
            (self.base / f.ruta_declarada).rename(self.base / (f.ruta_declarada + ".conservado"))
        self.assertEqual(verificar_diagnostico_archivo(ruta), d)

    def test_diagnostico_alterado_no_genera_informe(self):
        ruta, _ = self.guardar_diagnostico()
        original = leer(ruta)
        for campo in ("recomendaciones", "resumenEntreVistas", "limitaciones"):
            datos = copy.deepcopy(original)
            datos[campo] = []
            self.guardar(ruta, datos)
            with self.subTest(campo=campo), self.assertRaises(ErrorProcesamiento) as error:
                generar_informe(ruta)
            self.assertEqual(error.exception.codigo, "INTEGRIDAD")

    def test_informe_tiene_contextos_metricas_revisiones_y_limites(self):
        ruta, _ = self.guardar_diagnostico()
        texto = generar_informe(ruta)
        for fragmento in ("VISTA-inicio", "VISTA-cursos", "D-AC", "D-RE", "D-US", "3200", "4500",
                          "sin observaciones", "SIMULADO", "SHA-256", "Recomendaciones", "sin clasificación"):
            self.assertIn(fragmento, texto)

    def test_datos_de_informe_no_inyectan_tablas_o_html(self):
        self.manifiesto["titulo"] = "<script>alert(1)</script> | otra columna\n#otro"
        ruta, _ = self.guardar_diagnostico()
        texto = generar_informe(ruta)
        self.assertNotIn("<script>", texto)
        self.assertIn("&lt;script&gt;", texto)
        self.assertIn("\\| otra columna", texto)

    def test_cli_recorrido_y_destinos_exclusivos(self):
        self.guardar(self.ruta, self.manifiesto)
        salida = self.base / "diagnostico.json"
        informe = self.base / "informe.md"
        args = ["diagnosticar", str(self.ruta), "--salida", str(salida)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 0)
            self.assertEqual(main(["informe", str(salida), "--salida", str(informe)]), 0)
        antes = salida.read_bytes()
        informe_antes = informe.read_bytes()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 1)
            self.assertEqual(main(["informe", str(salida), "--salida", str(informe)]), 1)
            self.assertEqual(main(["diagnosticar", str(self.ruta), "--salida", str(self.ruta)]), 1)
        self.assertEqual(salida.read_bytes(), antes)
        self.assertEqual(informe.read_bytes(), informe_antes)

    def test_cli_error_no_crea_salida(self):
        self.grupo["fuentes"][0]["sha256"] = "0" * 64
        self.guardar(self.ruta, self.manifiesto)
        salida = self.base / "no_crear.json"
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["diagnosticar", str(self.ruta), "--salida", str(salida)]), 1)
        self.assertFalse(salida.exists())

    def test_json_invalido_y_archivo_ausente_se_informan(self):
        salida = self.base / "no_crear.json"
        for texto in ('{"vistas":[],"vistas":[]}', '{"x":NaN}', '{"x":1e999}'):
            self.ruta.write_text(texto, encoding="utf-8")
            with self.subTest(texto=texto), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["diagnosticar", str(self.ruta), "--salida", str(salida)]), 1)
            self.assertFalse(salida.exists())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["diagnosticar", str(self.base / "ausente.json"),
                                   "--salida", str(salida)]), 1)

    def test_repetir_no_cambia_decisiones_semanticas(self):
        primero = self.ejecutar().model_dump(mode="json")
        segundo = self.ejecutar().model_dump(mode="json")
        primero.pop("fecha_generacion")
        segundo.pop("fecha_generacion")
        self.assertEqual(primero, segundo)

    def test_grupos_de_una_vista_no_mezclan_perfiles_ni_metricas(self):
        grupo = copy.deepcopy(self.grupo)
        grupo.update(idGrupo="DESKTOP", idEvaluacion="EVAL-DESKTOP", perfilRendimiento="desktop")
        grupo["coincidencias"] = []
        fuente = {"idFuente": "desktop-lighthouse", "ruta": "desktop.json", "sha256": "0" * 64}
        grupo["fuentes"] = [fuente]
        self.manifiesto["vistas"][0]["grupos"].append(grupo)
        entrada = leer(self.base / self.fuente("lighthouse")["ruta"])["entradaImportada"]
        datos = entrada["entradaOriginal"]
        datos["configSettings"]["formFactor"] = "desktop"
        lote = clasificar_lote(importar_datos(datos, "lighthouse-result", "EVAL-DESKTOP",
                                             "VISTA-inicio", perfil="incremento-3"))
        self.guardar(self.base / fuente["ruta"], lote.model_dump(mode="json", by_alias=True))
        fuente["sha256"] = hashlib.sha256((self.base / fuente["ruta"]).read_bytes()).hexdigest()
        d = self.ejecutar()
        grupos = d.vistas[0].grupos
        self.assertEqual(len(grupos), 2)
        self.assertEqual(next(o.estado_vigente for o in grupos[0].observaciones
                              if o.id_indicador == "P-02"), "intermedio")
        self.assertEqual(next(o.estado_vigente for o in grupos[1].observaciones
                              if o.id_indicador == "P-02"), "no_evaluado")

    def test_contexto_wave_no_oculta_la_url_de_captura_original(self):
        self.reconstruir("wave", lambda w: w["captura"].update(
            url="https://simulado.invalid/otra-vista",
            contexto={**w["captura"]["contexto"], "url": self.manifiesto["vistas"][0]["url"]}))
        self.esperar_error("CONTEXTO_INCOMPATIBLE")

    def test_sel_anidado_conservado_sin_aplanar_identidad_del_elemento(self):
        self.reconstruir("axe", lambda a: a["violations"][0]["nodes"][1].update(
            target=[["iframe", "#otra-imagen"]]))
        g = self.ejecutar().vistas[0].grupos[0]
        o = next(o for o in g.observaciones if o.referencia.id_fuente == "inicio-axe"
                 and o.referencia.indice_nodo == 1)
        self.assertEqual(o.ubicacion, [["iframe", "#otra-imagen"]])

    def test_solo_favorables_o_no_aplicables_no_generan_recomendacion(self):
        self.grupo["coincidencias"] = []
        self.grupo["fuentes"] = [self.fuente("axe")]
        self.manifiesto["vistas"] = self.manifiesto["vistas"][:1]
        def cambio(a):
            a["violations"] = []
            a["incomplete"] = []
        self.reconstruir("axe", cambio)
        d = self.ejecutar()
        self.assertEqual(d.recomendaciones, [])
        self.assertEqual(d.vistas[0].grupos[0].hallazgos, [])

    def test_ruta_json_de_observaciones_llega_a_la_evidencia_embebida(self):
        d = self.ejecutar()
        fuentes = {f.id_fuente: f for f in d.fuentes}
        for vista in d.vistas:
            for g in vista.grupos:
                for o in g.observaciones:
                    valor = fuentes[o.referencia.id_fuente].lote.entrada_importada.entrada_original
                    for token in o.ruta_evidencia.strip("/").split("/"):
                        token = token.replace("~1", "/").replace("~0", "~")
                        valor = valor[int(token)] if isinstance(valor, list) else valor[token]
                    self.assertIsInstance(valor, dict)

    def test_historial_con_fechas_invertidas_no_se_integra(self):
        ref = self.fuente()
        datos = leer(self.base / ref["ruta"])
        resultado = next(r for r in datos["resultados"] if r["decision"]["revision"] == "pendiente")
        registro = {"idResultado": resultado["origen"]["idResultado"], "responsable": "SIMULADO",
                    "fechaHora": "2026-11-04T12:00:00-05:00", "estadoRevisado": "requiere_revision",
                    "fundamento": "SIMULADO", "evidencia": "SIMULADO"}
        for n, fecha in ((1, "2026-11-04T12:00:00-05:00"), (2, "2026-11-04T11:00:00-05:00")):
            datos["historialRevisiones"].append({
                "numero": n, "situacion": "realizada", "sha256LotePrevio": "0" * 64,
                "registro": {**registro, "fechaHora": fecha}, "decisionAutomatica": resultado["decision"]})
        self.actualizar_fuente("axe", datos)
        self.esperar_error("INTEGRIDAD")


if __name__ == "__main__":
    unittest.main()

