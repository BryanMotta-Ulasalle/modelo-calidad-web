"""Registra una decisión humana explícita sin borrar la decisión automática."""

import hashlib
from pathlib import Path

from pydantic import ValidationError

from .modelos import LoteProcesado, RevisionHumana, RevisionRegistrada
from .motor import ErrorProcesamiento, clasificar_lote, leer_json


def registrar_revision_archivo(ruta_lote: str | Path, ruta_registro: str | Path) -> LoteProcesado:
    contenido, datos = leer_json(ruta_lote)
    _, registro = leer_json(ruta_registro)
    try:
        lote = LoteProcesado.model_validate(datos)
        revision = RevisionHumana.model_validate(registro)
    except ValidationError as error:
        raise ErrorProcesamiento("FORMATO", f"revisión o lote inválidos: {error}") from error

    # Recalcular comprueba que no se haya reemplazado una decisión del motor.
    esperado = clasificar_lote(lote.entrada_importada)
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
    for numero, anterior in enumerate(lote.historial_revisiones, 1):
        resultado = por_id.get(anterior.registro.id_resultado)
        if (anterior.numero != numero or resultado is None
                or resultado.decision.revision != "pendiente"
                or anterior.decision_automatica != resultado.decision):
            raise ErrorProcesamiento("INTEGRIDAD", "historial de revisión incoherente")
    resultado = por_id.get(revision.id_resultado)
    if resultado is None:
        raise ErrorProcesamiento("RESULTADO_INEXISTENTE", "el ID no pertenece a este lote")
    if resultado.decision.revision != "pendiente":
        raise ErrorProcesamiento("REVISION_NO_REQUERIDA", "el resultado no tiene revisión pendiente")
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
