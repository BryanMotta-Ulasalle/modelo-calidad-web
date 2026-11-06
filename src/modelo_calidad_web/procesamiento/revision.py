"""Registra una decisión humana explícita sin borrar la decisión automática."""

import hashlib
from pathlib import Path

from pydantic import ValidationError

from .modelos import LoteProcesado, RevisionHumana, RevisionRegistrada
from .motor import ErrorProcesamiento, clasificar_lote, leer_json
from modelo_calidad_web.importacion.modelos import LoteImportado
from modelo_calidad_web.json_seguro import json_estricto


def comprobar_hash_intermedio(lote: LoteProcesado) -> str:
    texto = lote.texto_lote_importado
    if texto is None and lote.tipo_hash_entrada == "representacion_json":
        texto = lote.entrada_importada.model_dump_json(by_alias=True)
    if texto is None:
        return "no_comprobado_archivo_historico_ausente"
    if hashlib.sha256(texto.encode("utf-8")).hexdigest() != lote.sha256_lote_importado:
        raise ErrorProcesamiento("INTEGRIDAD", "hash del lote intermedio incoherente")
    try:
        recibido = LoteImportado.model_validate(json_estricto(texto))
    except ValueError as error:
        raise ErrorProcesamiento("INTEGRIDAD", "texto del lote intermedio inválido") from error
    if recibido != lote.entrada_importada:
        raise ErrorProcesamiento("INTEGRIDAD", "el archivo intermedio no corresponde a la entrada")
    return "comprobado"


def _validar_alcance(lote, revision, resultado):
    nodos = resultado.origen.datos_originales.get("nodes", []) if lote.motor_fuente == "axe-core" else []
    if revision.fecha_hora < lote.entrada_importada.fecha_hora:
        raise ErrorProcesamiento("FORMATO", "la revisión no puede preceder a la captura")
    if revision.alcance == "nodo":
        if not nodos or revision.indice_nodo >= len(nodos):
            raise ErrorProcesamiento("FORMATO", "índice de nodo inexistente para revisión")
    elif len(nodos) > 1 and revision.alcance != "resultado_completo":
        raise ErrorProcesamiento("FORMATO", "una regla con varios nodos exige alcance explícito")


def revision_vigente(lote, id_resultado, indice_nodo=None):
    candidatas = [r for r in lote.historial_revisiones
                  if r.registro.id_resultado == id_resultado and
                  (r.registro.alcance != "nodo" or r.registro.indice_nodo == indice_nodo)]
    return candidatas[-1] if candidatas else None


def validar_lote_procesado(lote: LoteProcesado) -> None:
    """Comprueba decisiones e historial antes de reutilizar el lote.

    Los hashes del historial enlazan archivos previos que deben custodiarse;
    sin esos archivos no se verifica la cadena ni la identidad del revisor.
    """
    # Recalcular comprueba que no se haya reemplazado una decisión del motor.
    esperado = clasificar_lote(lote.entrada_importada)
    comprobar_hash_intermedio(lote)
    if (lote.version_reglas != esperado.version_reglas or lote.sha256_reglas != esperado.sha256_reglas
            or lote.motor_fuente != esperado.motor_fuente
            or lote.sha256_catalogo_mapeos != esperado.sha256_catalogo_mapeos
            or lote.cobertura_indicadores != esperado.cobertura_indicadores
            or lote.contexto_adicional != esperado.contexto_adicional
            or lote.fuentes_fuera_cobertura != esperado.fuentes_fuera_cobertura
            or lote.limitaciones != esperado.limitaciones
            or lote.resultados != esperado.resultados):
        raise ErrorProcesamiento("INTEGRIDAD", "la clasificación no corresponde a las reglas y fuente conservadas")

    por_id = {r.origen.id_resultado: r for r in lote.resultados}
    fechas = {}
    for numero, anterior in enumerate(lote.historial_revisiones, 1):
        resultado = por_id.get(anterior.registro.id_resultado)
        if (anterior.numero != numero or resultado is None
                or resultado.decision.revision != "pendiente"
                or anterior.decision_automatica != resultado.decision):
            raise ErrorProcesamiento("INTEGRIDAD", "historial de revisión incoherente")
        _validar_alcance(lote, anterior.registro, resultado)
        id_resultado = anterior.registro.id_resultado
        fecha = anterior.registro.fecha_hora
        if id_resultado in fechas and fecha < fechas[id_resultado]:
            raise ErrorProcesamiento("INTEGRIDAD", "historial de revisión no cronológico")
        fechas[id_resultado] = fecha


def registrar_revision_archivo(ruta_lote: str | Path, ruta_registro: str | Path) -> LoteProcesado:
    contenido, datos = leer_json(ruta_lote)
    _, registro = leer_json(ruta_registro)
    try:
        lote = LoteProcesado.model_validate(datos)
        revision = RevisionHumana.model_validate(registro)
    except ValidationError as error:
        raise ErrorProcesamiento("FORMATO", f"revisión o lote inválidos: {error}") from error
    validar_lote_procesado(lote)
    por_id = {r.origen.id_resultado: r for r in lote.resultados}
    resultado = por_id.get(revision.id_resultado)
    if resultado is None:
        raise ErrorProcesamiento("RESULTADO_INEXISTENTE", "el ID no pertenece a este lote")
    if resultado.decision.revision != "pendiente":
        raise ErrorProcesamiento("REVISION_NO_REQUERIDA", "el resultado no tiene revisión pendiente")
    _validar_alcance(lote, revision, resultado)
    fechas_previas = [r.registro.fecha_hora for r in lote.historial_revisiones
                     if r.registro.id_resultado == revision.id_resultado]
    if fechas_previas and revision.fecha_hora < max(fechas_previas):
        raise ErrorProcesamiento("FORMATO", "la revisión no puede ser anterior a la previa del resultado")

    salida = lote.model_copy(deep=True)
    salida.historial_revisiones.append(RevisionRegistrada(
        numero=len(salida.historial_revisiones) + 1,
        sha256_lote_previo=hashlib.sha256(contenido).hexdigest(),
        registro=revision,
        decision_automatica=resultado.decision.model_copy(deep=True),
    ))
    return salida
