"""Clasificación por regla; no consolida indicadores ni genera diagnósticos."""

import hashlib
import json
import math
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from modelo_calidad_web.dominio.enumeraciones import EstadoNormalizado, TipoResultado
from modelo_calidad_web.json_seguro import json_estricto
from modelo_calidad_web.importacion import ErrorImportacion, LoteImportado, ResultadoImportado, importar_datos

from .modelos import CoberturaFuente, CoberturaIndicador, Decision, LoteProcesado, ResultadoProcesado


class ErrorProcesamiento(ValueError):
    def __init__(self, codigo: str, detalle: str):
        self.codigo = codigo
        super().__init__(detalle)


def _json(objeto: Any) -> str:
    return json.dumps(objeto, ensure_ascii=False, sort_keys=True, allow_nan=False)


def leer_json(ruta: str | Path) -> tuple[bytes, Any]:
    try:
        contenido = Path(ruta).read_bytes()
        return contenido, json_estricto(contenido.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise ErrorProcesamiento("FORMATO", f"JSON UTF-8 inválido: {error}") from error


def cargar_reglas() -> tuple[dict, str]:
    contenido = files("modelo_calidad_web").joinpath("catalogos/reglas_clasificacion_v1.json").read_bytes()
    return json_estricto(contenido.decode("utf-8")), hashlib.sha256(contenido).hexdigest()


def normalizar_metrica(valor: Any, unidad: str | None, unidad_destino: str) -> float:
    """Conversión sin redondeo; el llamador conserva el valor original aparte."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorProcesamiento("DATO_INVALIDO", "la métrica debe ser numérica, sin booleanos")
    try:
        numero = float(valor)
    except OverflowError as error:
        raise ErrorProcesamiento("DATO_INVALIDO", "la métrica excede el rango numérico") from error
    if not math.isfinite(numero) or numero < 0:
        raise ErrorProcesamiento("DATO_INVALIDO", "la métrica debe ser finita y no negativa")
    reglas, _ = cargar_reglas()
    if unidad_destino == "unitless" and unidad in {"unitless", "proporcion"}:
        return numero
    if unidad_destino != "ms" or unidad not in reglas["conversionTiempo"]:
        raise ErrorProcesamiento("UNIDAD_NO_ADMITIDA", f"no se puede convertir {unidad!r} a {unidad_destino}")
    normalizado = numero * reglas["conversionTiempo"][unidad]
    if not math.isfinite(normalizado):
        raise ErrorProcesamiento("DATO_INVALIDO", "la conversión excede el rango numérico")
    return normalizado


def _comprobar_lote(lote: LoteImportado, reglas: dict) -> None:
    """Repite la importación para detectar cambios entre fuente y etapa intermedia.

    La coherencia y los hashes no prueban la autoría ni una captura auténtica.
    """
    if reglas["versionesLoteAdmitidas"].get(lote.version_esquema) != lote.version_catalogo_mapeos:
        raise ErrorProcesamiento("VERSION_NO_ADMITIDA", "se requiere lote 0.2.0/mapeos 1.1.0 o 0.3.0/mapeos 2.0.0")
    try:
        if hashlib.sha256(lote.texto_original.encode("utf-8")).hexdigest() != lote.sha256_original:
            raise ErrorProcesamiento("INTEGRIDAD", "sha256Original no coincide con textoOriginal")
        fuente = json_estricto(lote.texto_original)
        if _json(fuente) != _json(lote.entrada_original):
            raise ErrorProcesamiento("INTEGRIDAD", "entradaOriginal difiere del texto conservado")
        reconstruido = importar_datos(
            fuente, lote.formato_fuente, lote.id_evaluacion, lote.id_modulo_vista,
            texto_original=lote.texto_original,
            ejecutor=lote.contexto.get("ejecutorDeclarado"),
            perfil="incremento-3" if lote.version_esquema == "0.3.0" else "incremento-2",
        )
        recibido = lote.model_dump(mode="json", by_alias=True)
        esperado = reconstruido.model_dump(mode="json", by_alias=True)
        evidencia = recibido["contexto"].pop("evidenciaEjecucion", None)
        if evidencia is not None:
            if lote.formato_fuente != "axe-core-playwright" or not isinstance(evidencia, dict):
                raise ErrorProcesamiento("INTEGRIDAD", "evidenciaEjecucion inesperada")
            manifiesto = evidencia.get("manifiesto", {})
            if not isinstance(manifiesto, dict) or any((
                manifiesto.get("sha256Fuente") != lote.sha256_original,
                manifiesto.get("urlFinal") != fuente.get("url"),
                manifiesto.get("testEngine") != fuente.get("testEngine"),
                evidencia.get("tipo") != "manifiesto_vinculado_por_sha256",
            )):
                raise ErrorProcesamiento("INTEGRIDAD", "manifiesto no coincide con la fuente conservada")
        if _json(recibido) != _json(esperado):
            raise ErrorProcesamiento("INTEGRIDAD", "el lote no coincide con la importación de su fuente")
    except ErrorImportacion as error:
        raise ErrorProcesamiento(error.codigo, str(error)) from error
    except (ValueError, TypeError, OverflowError) as error:
        if isinstance(error, ErrorProcesamiento):
            raise
        raise ErrorProcesamiento("FORMATO", f"fuente no utilizable: {error}") from error


def _decision(reglas, id_regla, estado, motivo, motivo_prioridad, referencias,
              *, prioridad=None, valor=None, unidad=None, condiciones=None):
    return Decision(
        id_regla=id_regla, version_reglas=reglas["version"], referencias=referencias,
        estado_normalizado=estado, prioridad=prioridad, motivo_estado=motivo,
        motivo_prioridad=motivo_prioridad, valor_normalizado=valor,
        unidad_normalizada=unidad, condiciones=condiciones or {},
        revision="pendiente" if estado == "requiere_revision" else "no_requerida",
    )


def _clasificar(resultado: ResultadoImportado, lote: LoteImportado, reglas: dict) -> Decision:
    if lote.formato_fuente == "lighthouse-result" and resultado.identificador_origen in reglas["auditoriasTecnicas"]:
        regla = reglas["auditoriasTecnicas"][resultado.identificador_origen]
        if lote.version_herramienta not in regla["versionesAdmitidas"]:
            raise ErrorProcesamiento("VERSION_NO_ADMITIDA", "auditoría técnica sin contrato de versión admitido")
        modo, score = resultado.estado_original, resultado.valor_original
        prioridad = None
        if modo == "error" or resultado.datos_originales.get("errorMessage"):
            estado, motivo = "no_evaluado", "auditoria_con_error"
        elif modo == "notApplicable":
            estado, motivo = "no_evaluado", "no_aplicable"
        elif score == 1:
            estado, motivo = "favorable", "auditoria_ejecutada_sin_hallazgo_para_esta_comprobacion"
        elif resultado.identificador_origen == "errors-in-console":
            estado, motivo, prioridad = "requiere_revision", "revisar_impacto_de_errores_observados", "revision"
        else:
            estado, motivo = "desfavorable", "auditoria_tecnica_informada_como_fallida"
        return _decision(reglas, regla["regla"], estado, motivo,
                         "revision_del_impacto" if prioridad else "sin_regla_de_severidad_para_auditoria",
                         [reglas["referenciaDiseno"], regla["fuente"]], prioridad=prioridad,
                         condiciones={"modoAuditoria": modo, "versionAdmitida": lote.version_herramienta,
                                      "alcance": "auditoria_y_ejecucion"})

    if lote.formato_fuente == "lighthouse-result":
        regla = reglas["metricas"][resultado.identificador_origen]
        valor = normalizar_metrica(resultado.valor_original, resultado.unidad_original, regla["unidad"])
        perfil = lote.contexto["configSettings"].get("formFactor")
        condiciones = {"perfilObservado": perfil, "perfilAdmitido": regla["perfil"],
                       "favorableMax": regla["favorableMax"], "intermedioMax": regla["intermedioMax"],
                       "comparacionSinRedondeo": True, "tipoMedicion": "laboratorio",
                       "modoAuditoria": resultado.datos_originales.get("scoreDisplayMode")}
        referencias = [reglas["referenciaDiseno"], regla["fuente"]]
        modo = resultado.datos_originales.get("scoreDisplayMode")
        if modo == "error" or resultado.datos_originales.get("errorMessage"):
            motivo, estado = "auditoria_con_error", "no_evaluado"
        elif modo == "notApplicable":
            motivo, estado = "no_aplicable", "no_evaluado"
        elif modo not in (None, "numeric"):
            raise ErrorProcesamiento("FORMATO", f"modo de auditoría no admitido para métrica: {modo}")
        elif regla["perfil"] and perfil != regla["perfil"]:
            motivo = "perfil_ausente" if perfil is None else "perfil_sin_regla_admitida"
            estado = "no_evaluado"
        else:
            estado = ("favorable" if valor <= regla["favorableMax"] else
                      "intermedio" if valor <= regla["intermedioMax"] else "desfavorable")
            motivo = "valor_comparado_con_umbrales_inclusivos"
        return _decision(reglas, regla["regla"], estado, motivo,
                         "sin_regla_de_prioridad_para_metrica", referencias,
                         valor=valor, unidad=regla["unidad"], condiciones=condiciones)

    if lote.formato_fuente in {"wave-extension-captura-v1", "wave-extension-captura-v2"}:
        categoria = reglas["categoriasWave"].get(resultado.identificador_origen)
        if categoria in {"feature", "structure", "aria"}:
            return _decision(reglas, "AC-03", None, "evidencia_contextual_sin_juicio_de_calidad",
                             "evidencia_contextual_no_se_prioriza", reglas["referenciasWave"],
                             condiciones={"categoriaPorMapeo": categoria})
        if categoria == "alert":
            return _decision(reglas, "AC-02", "requiere_revision", "alerta_wave_requiere_interpretacion",
                             "alerta_no_equivale_a_infraccion_confirmada", reglas["referenciasWave"],
                             prioridad="revision", condiciones={"categoriaPorMapeo": categoria})
        if categoria not in {"error", "contrast"}:
            raise ErrorProcesamiento("SIN_REGLA", "categoría WAVE sin regla admitida")
        politica = reglas["prioridadWave"][resultado.identificador_origen]
        return _decision(reglas, "AC-01", "desfavorable", "categoria_wave_error_o_contraste",
                         politica["fundamento"], [*reglas["referenciasWave"], politica["fuente"]],
                         prioridad=politica["prioridad"],
                         condiciones={"categoriaPorMapeo": categoria, "procedencia": lote.procedencia,
                                      "prioridadEsDecisionDelModelo": True})

    grupo = resultado.estado_original
    regla = reglas["gruposAxe"][grupo]
    impacto = resultado.valor_original
    prioridad = None
    id_regla = regla["regla"]
    motivos = {"violations": "infraccion_informada_por_regla",
               "incomplete": "resultado_incierto_requiere_revision",
               "passes": "comprobacion_ejecutada_sin_infraccion_para_esta_regla",
               "inapplicable": "no_aplicable"}
    if grupo == "violations":
        prioridad = reglas["prioridadAxe"].get(impacto) if isinstance(impacto, str) else None
        motivo_prioridad = "impacto_axe_mapeado" if prioridad else "impacto_ausente_o_no_reconocido"
        if prioridad is None:
            id_regla = "AC-08"
    elif grupo == "incomplete":
        prioridad, motivo_prioridad = "revision", "incertidumbre_no_equivale_a_severidad_confirmada"
    else:
        motivo_prioridad = "no_corresponde_priorizar_este_resultado"
    return _decision(reglas, id_regla, regla["estado"], motivos[grupo], motivo_prioridad,
                     reglas["referenciasAxe"], prioridad=prioridad,
                     condiciones={"grupoFuente": grupo, "impactoOriginal": impacto,
                                  "alcance": "regla_y_ejecucion", "dimensionPrincipal": resultado.id_dimension.value})


def _adicionales_axe(lote: LoteImportado) -> tuple[list[ResultadoImportado], list[CoberturaFuente]]:
    """Extensión de procesamiento; el comando importar sigue entregando 0.2.0."""
    mapas = json.loads(files("modelo_calidad_web").joinpath("catalogos/mapeos_fuentes_v1.json").read_text(encoding="utf-8"))["mapeos"]["axe-core-playwright"]
    adicionales, fuera = [], []
    for grupo in ("passes", "inapplicable"):
        for indice, item in enumerate(lote.entrada_original[grupo]):
            ruta = f"/{grupo}/{indice}"
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
                raise ErrorProcesamiento("FORMATO", f"regla inválida en {ruta}")
            identificador = item["id"]
            if identificador not in mapas:
                fuera.append(CoberturaFuente(identificador_origen=identificador, ruta_origen=ruta,
                                            motivo="fuera_catalogo_admitido"))
                continue
            nodos = item.get("nodes")
            if not isinstance(nodos, list) or (grupo == "passes" and not nodos):
                raise ErrorProcesamiento("DATOS_INSUFICIENTES", f"nodes no utilizable en {ruta}")
            for nodo in nodos:
                if (not isinstance(nodo, dict) or not isinstance(nodo.get("target"), list)
                        or not _selector_valido(nodo["target"])):
                    raise ErrorProcesamiento("DATOS_INSUFICIENTES", f"target no utilizable en {ruta}")
            mapa = mapas[identificador]
            adicionales.append(ResultadoImportado(
                idResultado=f"axe-core-playwright:{grupo}:{identificador}:{indice}",
                identificadorOrigen=identificador, idIndicador=mapa["indicador"],
                idDimension=mapa["dimension"], referenciaTecnica=mapa["referencias"],
                tipoResultado=TipoResultado.AUDITORIA, valorOriginal=item.get("impact"),
                ubicacionElemento=lote.contexto["url"], estadoOriginal=grupo,
                evidencia={"nodes": nodos, "impact": item.get("impact")},
                rutaOrigen=ruta, datosOriginales=item,
            ))
    return adicionales, fuera


def _selector_valido(valor: Any) -> bool:
    if isinstance(valor, str):
        return bool(valor.strip())
    return isinstance(valor, list) and bool(valor) and all(_selector_valido(item) for item in valor)


def _cobertura(lote, resultados, mapas):
    indicadores = json.loads(files("modelo_calidad_web").joinpath("catalogos/indicadores.json").read_text(encoding="utf-8"))
    correspondencias = mapas["mapeos"][lote.formato_fuente]
    salida = []
    for indicador in indicadores:
        id_indicador = indicador["id"]
        admitidos = [id_fuente for id_fuente, mapa in correspondencias.items() if mapa["indicador"] == id_indicador]
        cantidad = sum(r.origen.id_indicador == id_indicador for r in resultados)
        if indicador.get("contextual") and lote.formato_fuente == "lighthouse-result":
            situacion, motivo = "contextual", "puntuacion_compuesta_conservada_sin_agregacion"
        elif cantidad:
            situacion, motivo = "con_resultados", "cobertura_limitada_a_reglas_y_elementos_informados"
        elif admitidos:
            situacion, motivo = "sin_resultados_en_fuente", "ausencia_de_resultado_no_equivale_a_favorable"
            if id_indicador == "U-01" and lote.version_herramienta == "13.5.0":
                motivo = "viewport_retirada_en_lighthouse_13_no_se_asume_equivalencia_de_viewport_insight"
        else:
            situacion, motivo = "fuera_del_formato", "este_formato_no_aporta_una_regla_admitida_para_el_indicador"
        salida.append(CoberturaIndicador(id_indicador=id_indicador, situacion=situacion,
                                        resultados_observados=cantidad, identificadores_admitidos=admitidos, motivo=motivo))
    return salida


def clasificar_lote(lote: LoteImportado, *, archivo_intermedio: bytes | None = None) -> LoteProcesado:
    reglas, hash_reglas = cargar_reglas()
    _comprobar_lote(lote, reglas)
    if archivo_intermedio is not None:
        try:
            recibido = LoteImportado.model_validate(json_estricto(archivo_intermedio.decode("utf-8")))
        except (ValueError, UnicodeError) as error:
            raise ErrorProcesamiento("FORMATO", f"lote intermedio inválido: {error}") from error
        if _json(recibido.model_dump(mode="json")) != _json(lote.model_dump(mode="json")):
            raise ErrorProcesamiento("INTEGRIDAD", "los bytes intermedios no corresponden al lote")
        contenido = archivo_intermedio
    else:
        contenido = lote.model_dump_json(by_alias=True).encode("utf-8")
    adicionales, fuera = (_adicionales_axe(lote) if lote.formato_fuente == "axe-core-playwright" and lote.version_esquema == "0.2.0" else
                          ([], [CoberturaFuente.model_validate(r) for r in lote.contexto.get("reglasFueraCobertura", [])]))
    resultados = [ResultadoProcesado(origen=r.model_copy(deep=True), etapa_origen=etapa,
                                    decision=_clasificar(r, lote, reglas))
                  for etapa, entradas in (("lote_importado", lote.resultados), ("fuente_conservada", adicionales))
                  for r in entradas]
    contexto = {}
    archivo_mapeos = "mapeos_fuentes_v2.json" if lote.version_catalogo_mapeos == "2.0.0" else "mapeos_fuentes_v1.json"
    bytes_mapeos = files("modelo_calidad_web").joinpath("catalogos/" + archivo_mapeos).read_bytes()
    mapas = json.loads(bytes_mapeos)
    if lote.formato_fuente == "lighthouse-result":
        score = lote.entrada_original["categories"]["performance"].get("score")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1):
            raise ErrorProcesamiento("DATO_INVALIDO", "puntuación contextual Lighthouse fuera de 0..1")
        contexto["rendimientoCompuesto"] = {"idIndicador": "P-06", "valorOriginal": score,
                                            "valorContextual": score * 100 if score is not None else None,
                                            "unidadContextual": "0-100", "uso": "solo_contexto_sin_agregacion"}
    return LoteProcesado(
        version_reglas=reglas["version"], sha256_reglas=hash_reglas,
        sha256_catalogo_mapeos=hashlib.sha256(bytes_mapeos).hexdigest(),
        sha256_lote_importado=hashlib.sha256(contenido).hexdigest(),
        tipo_hash_entrada="archivo" if archivo_intermedio is not None else "representacion_json",
        texto_lote_importado=contenido.decode("utf-8"),
        fecha_procesamiento=datetime.now(timezone.utc),
        motor_fuente={"axe-core-playwright": "axe-core", "wave-extension-captura-v1": "WAVE Extension", "wave-extension-captura-v2": "WAVE Extension",
                      "lighthouse-result": "Lighthouse"}[lote.formato_fuente],
        entrada_importada=lote.model_copy(deep=True), resultados=resultados,
        fuentes_fuera_cobertura=fuera, contexto_adicional=contexto,
        cobertura_indicadores=_cobertura(lote, resultados, mapas),
        limitaciones=[
            "Clasificación por regla y ejecución; sin consolidación, diagnóstico ni puntaje global.",
            "No certifica WCAG ni evalúa usabilidad completa.",
            "WAVE: transcripción documentada; prioridad operativa del modelo, no severidad oficial de WAVE.",
            "Rendimiento: umbrales móviles; CLS independiente del perfil. Datos de laboratorio.",
            "La cobertura de A-08/A-09 y demás indicadores es parcial por regla; no acredita accesibilidad completa.",
            "U-01 admite viewport de Lighthouse 12.8.2; no interpreta viewport-insight de 13.5.0 como equivalente.",
            "Los hashes verifican coherencia de archivos, no autoría ni procedencia de una captura.",
        ],
    )


def clasificar_archivo(ruta: str | Path) -> LoteProcesado:
    contenido, datos = leer_json(ruta)
    try:
        lote = LoteImportado.model_validate(datos)
    except ValidationError as error:
        raise ErrorProcesamiento("FORMATO", f"no es un lote importado válido: {error}") from error
    return clasificar_lote(lote, archivo_intermedio=contenido)
