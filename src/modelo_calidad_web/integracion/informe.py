"""Informe Markdown legible a partir de un diagnóstico recalculado y verificado."""

import html
import json

from .motor import verificar_diagnostico_archivo


def _texto(valor):
    if valor is None:
        return "sin dato"
    if isinstance(valor, (dict, list)):
        valor = json.dumps(valor, ensure_ascii=False, sort_keys=True)
    return html.escape(str(valor)).replace("\\", "\\\\").replace("|", "\\|").replace(
        "\n", "<br>").replace("\r", "").replace("[", "\\[").replace("]", "\\]").replace(
        "*", "\\*").replace("_", "\\_").replace(chr(96), "\\" + chr(96)).replace("#", "\\#")


def _tabla(cabeceras, filas):
    return ["| " + " | ".join(cabeceras) + " |",
            "| " + " | ".join("---" for _ in cabeceras) + " |"] + [
        "| " + " | ".join(_texto(c) for c in fila) + " |" for fila in filas
    ] + [""]


def generar_informe(ruta_diagnostico):
    diagnostico = verificar_diagnostico_archivo(ruta_diagnostico)
    manifiesto = diagnostico.manifiesto
    lineas = [
        "# Diagnóstico estructurado de calidad web", "",
        f"**Caso:** {_texto(manifiesto.id_caso)} — {_texto(manifiesto.titulo)}", "",
        f"**Tipo de datos declarado:** {_texto(manifiesto.tipo_datos)}. "
        "Esta etiqueta no demuestra su autenticidad.", "",
        f"**Alcance:** {_texto(manifiesto.alcance)}", "",
        f"**Generación:** {_texto(diagnostico.fecha_generacion.isoformat())}. "
        f"Integrador {diagnostico.version_integrador}; reglas {diagnostico.version_reglas_integracion}.", "",
        "## Vistas y cobertura", "",
        "Los conteos describen observaciones por regla/nodo y hallazgos consolidados. "
        "No se calcula un estado global ni un puntaje de calidad. "
        "El resumen entre vistas es descriptivo; las comparaciones requieren protocolo explícito.", "",
    ]
    for vista in diagnostico.vistas:
        lineas += [f"### {_texto(vista.id_modulo_vista)}: {_texto(vista.nombre)}", "",
                   f"URL: {_texto(vista.url)}", ""]
        declarada = next(v for v in manifiesto.vistas if v.id_modulo_vista == vista.id_modulo_vista)
        if not vista.grupos:
            lineas += ["Vista seleccionada sin fuentes: accesibilidad, rendimiento y condiciones "
                       "técnicas de usabilidad permanecen sin datos.", ""]
        for grupo in vista.grupos:
            condiciones = next(g for g in declarada.grupos if g.id_grupo == grupo.id_grupo)
            lineas += [f"#### Grupo {_texto(grupo.id_grupo)}", "",
                       f"Evaluación: {_texto(condiciones.id_evaluacion)}. "
                       f"Capturas entre {_texto(condiciones.inicio.isoformat())} "
                       f"y {_texto(condiciones.fin.isoformat())}.", "",
                       f"Perfil de acceso: {_texto(condiciones.perfil_acceso)}. "
                       f"Perfil de rendimiento: {_texto(condiciones.perfil_rendimiento)}.", "",
                       f"Condiciones declaradas: {_texto(condiciones.condiciones_declaradas)}", "",
                       f"Justificación declarada de comparabilidad dentro del grupo: "
                       f"{_texto(condiciones.justificacion_comparabilidad)}", ""]
            for dimension in grupo.dimensiones:
                lineas += [f"**{_texto(dimension.nombre)} ({dimension.id_dimension})**", ""]
                lineas += _tabla(
                    ["Indicador", "Situación", "Resultados fuente", "Observaciones por estado", "Hallazgos"],
                    [(i.id_indicador + " " + i.nombre, i.situacion.replace("_", " "), i.resultados_fuente,
                      {k.replace("_", " "): v for k, v in i.estados_observados.items() if v}, ", ".join(i.ids_hallazgos))
                     for i in dimension.indicadores])
                for indicador in dimension.indicadores:
                    lineas += [f"- Alcance de {_texto(indicador.id_indicador)}: "
                               f"{_texto(indicador.limitacion)}"]
                    for metrica in indicador.metricas:
                        lineas += [
                            f"- {_texto(indicador.id_indicador)} / {_texto(metrica['idFuente'])}: "
                            f"{_texto(metrica['valorOriginal'])} {_texto(metrica['unidadOriginal'])}; "
                            f"normalizado {_texto(metrica['valorNormalizado'])} "
                            f"{_texto(metrica['unidadNormalizada'])}; estado {_texto(metrica['estado'])}. "
                            f"Condiciones: {_texto(metrica['condiciones'])}.",
                        ]
                    for contexto in indicador.contexto:
                        lineas += [f"- P-06 contextual, sin clasificación: {_texto(contexto)}."]
                    if indicador.situacion == "sin_observaciones":
                        for id_fuente, cobertura in indicador.cobertura_por_fuente.items():
                            if cobertura["situacion"] == "sin_resultados_en_fuente":
                                lineas += [f"- {_texto(indicador.id_indicador)} / {_texto(id_fuente)}: "
                                           f"{_texto(cobertura['motivo'])}."]
                lineas += [""]
            lineas += ["**Observaciones y trazabilidad de origen**", ""]
            lineas += _tabla(
                ["ID", "Indicador", "Fuente / resultado / nodo", "Ubicación",
                 "Automático → vigente", "Prioridad automática", "Revisión pendiente"],
                [(o.id_observacion, o.id_indicador,
                  f"{o.referencia.id_fuente} / {o.referencia.id_resultado} / {o.referencia.indice_nodo}",
                  o.ubicacion, f"{o.estado_automatico} → {o.estado_vigente}",
                  o.prioridad_automatica, o.pendiente_revision) for o in grupo.observaciones])
            lineas += ["**Hallazgos y coincidencias**", ""]
            lineas += _tabla(
                ["Hallazgo", "Indicador", "Estado", "Observaciones", "Coincidencia", "Prioridades observadas"],
                [(h.id_hallazgo, h.id_indicador, h.estado, h.ids_observaciones,
                  h.id_coincidencia, h.prioridades_observadas) for h in grupo.hallazgos])
            for h in grupo.hallazgos:
                enlaces = ", ".join(f"[{i}](#observacion-{i})" for i in h.ids_observaciones)
                lineas += [f'<a id="hallazgo-{h.id_hallazgo}"></a>',
                           f"- {h.id_hallazgo}: {enlaces}"]
            for o in grupo.observaciones:
                id_fuente = o.referencia.id_fuente
                lineas += [f'<a id="observacion-{o.id_observacion}"></a>',
                           f"- {o.id_observacion} → [fuente {id_fuente}](#fuente-{id_fuente}); "
                           f"ruta de evidencia: {_texto(o.ruta_evidencia)}."]
            for coincidencia in condiciones.coincidencias:
                lineas += [
                    f"- Coincidencia {_texto(coincidencia.id_coincidencia)}: "
                    f"{_texto(coincidencia.problema_comun)}. Elemento declarado: "
                    f"{_texto(coincidencia.elemento_canonico)}. Responsable declarado: "
                    f"{_texto(coincidencia.responsable)}, {_texto(coincidencia.fecha_hora.isoformat())}. "
                    f"Fundamento: {_texto(coincidencia.fundamento)}. "
                    f"Evidencia: {_texto(coincidencia.evidencia)}.",
                ]
            for o in grupo.observaciones:
                if o.revision_vigente:
                    r = o.revision_vigente.registro
                    lineas += [f"- Revisión vigente de {_texto(o.id_observacion)}: "
                               f"{_texto(r.responsable)}, {_texto(r.fecha_hora.isoformat())}; "
                               f"{_texto(r.fundamento)}. Evidencia: {_texto(r.evidencia)}."]
            lineas += [""]
    lineas += ["## Comparaciones entre vistas", ""]
    if not diagnostico.comparaciones:
        lineas += ["Sin comparación autorizada por un protocolo de condiciones equivalentes.", ""]
    for comparacion in diagnostico.comparaciones:
        lineas += [f"### {_texto(comparacion['idComparacion'])}", "",
                   f"Protocolo: {_texto(comparacion['protocolo'])}. "
                   f"Condiciones comunes: {_texto(comparacion['condicionesComunes'])}.", "",
                   _texto(comparacion["limite"]), ""]
        for metrica in comparacion["metricas"]:
            lineas += [f"**{_texto(metrica['idIndicador'])}: {_texto(metrica['situacion'])}**. "
                       f"Motivo: {_texto(metrica['motivo'])}.", ""]
            lineas += _tabla(["Vista / grupo", "Mediciones conservadas", "Diferencia respecto al primero"], [
                (f"{f['idModuloVista']} / {f['idGrupo']}", f["mediciones"],
                 f.get("diferenciaRespectoPrimerGrupo")) for f in metrica["filas"]])
        lineas += [f"Cobertura por grupo: {_texto(comparacion['coberturaPorGrupo'])}", ""]
    lineas += ["## Recomendaciones vinculadas a la evidencia", "",
               "El orden es técnico y orientativo. Las acciones deberán verificarse; no prueban "
               "mejora ni causas del funcionamiento interno.", ""]
    if not diagnostico.recomendaciones:
        lineas += ["Sin recomendaciones a partir de los estados recibidos. "
                   "Esto no acredita calidad completa ni conformidad.", ""]
    for r in diagnostico.recomendaciones:
        lineas += [f"### {_texto(r.id_recomendacion)} — {_texto(r.id_indicador)}", "",
                   f"Vista/grupo: {_texto(r.id_modulo_vista)} / {_texto(r.id_grupo)}. "
                   f"Hallazgo: [{r.id_hallazgo}](#hallazgo-{r.id_hallazgo}). Tipo: {_texto(r.tipo)}.", "",
                   _texto(r.accion), "",
                   f"Observaciones: {_texto(r.ids_observaciones)}. "
                   f"Prioridades originales: {_texto(r.prioridades_observadas)}.", "",
                   f"Elementos del mismo indicador/estado en el grupo: mínimo identificado "
                   f"{r.elementos_afectados_minimos}; máximo de ubicaciones conservadas "
                   f"{r.elementos_observados_maximos}. Vistas con la misma comprobación/estado "
                   f"bajo protocolo compatible: {r.vistas_con_misma_comprobacion}. "
                   f"Revisiones asociadas: {r.casos_revision_asociados}.", "",
                   _texto(r.criterio_desempate), "",
                   f"Referencias: {_texto(r.referencias)}", ""]
    lineas += ["## Fuentes, versiones y límites", "",
               f"SHA-256 del manifiesto: {diagnostico.sha256_manifiesto}", "",
               f"SHA-256 de reglas de integración: {diagnostico.sha256_reglas_integracion}", "",
               "Cada fuente conserva texto íntegro del archivo clasificado, lote, fuente original "
               "e historial en el JSON del diagnóstico. La ruta de evidencia de cada observación "
               "es relativa a entradaOriginal del lote fuente. Los IDs permiten recorrer "
               "recomendación → hallazgo → observación → resultado → fuente. "
               "Los límites de fuente citados al final corresponden a la etapa anterior de clasificación; "
               "la integración añade el diagnóstico sin alterar esos registros históricos.", ""]
    lineas += _tabla(
        ["Fuente", "Archivo declarado", "SHA-256 clasificado", "Herramienta / versión", "Captura"],
        [(f.id_fuente, f.ruta_declarada, f.sha256,
          f"{f.lote.motor_fuente} / {f.lote.entrada_importada.version_herramienta}",
          f.lote.entrada_importada.fecha_hora.isoformat()) for f in diagnostico.fuentes])
    for limite in diagnostico.limitaciones:
        lineas += [f"- {_texto(limite)}"]
    lineas += [""]
    for f in diagnostico.fuentes:
        lineas += [f'<a id="fuente-{f.id_fuente}"></a>',
                   f"### Límites de la fuente {_texto(f.id_fuente)}", "",
                   f"Clasificador/esquema: {f.lote.version_motor} / {f.lote.version_esquema}; "
                   f"reglas {f.lote.version_reglas}; mapeos {f.lote.entrada_importada.version_catalogo_mapeos}.", "",
                   f"SHA-256 de clasificación: {f.sha256}. "
                   f"SHA-256 de fuente original: {f.lote.entrada_importada.sha256_original}.", ""]
        lineas += [f"Verificación de la huella intermedia: "
                   f"{_texto(f.verificacion_hash_intermedio)}.", ""]
        lineas += [f"- {_texto(l)}" for l in f.lote.limitaciones]
        lineas += [""]
    return "\n".join(lineas) + "\n"

