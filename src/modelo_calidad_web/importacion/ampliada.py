"""Adaptadores explícitos del incremento 3; el perfil anterior se conserva."""

import copy

from modelo_calidad_web.dominio.enumeraciones import Herramienta, TipoResultado

from .importadores import (
    ErrorImportacion, _axe, _formato, _insuficiente, _lighthouse, _lista, _mapa,
    _objeto, _objetivo_axe, _resultado, _texto, _wave,
)


def wave_ampliado(datos, formatos):
    if datos.get("formato") != "wave-extension-captura-v2":
        _formato("se requiere captura WAVE v2 con categoría explícita")
    if datos.get("procedencia") not in {"transcripcion_manual", "captura_documentada_asistida"}:
        _formato("WAVE v2 requiere procedencia documentada, no una exportación JSON nativa")
    copia = copy.deepcopy(datos)
    copia["formato"] = "wave-extension-captura-v1"
    copia["procedencia"] = "transcripcion_manual"  # Reutiliza solo validaciones de la estructura anterior.
    formatos_compatibles = {"wave-extension-captura-v1": formatos["wave-extension-captura-v2"]}
    nombre, procedencia, herramienta, version, fecha, contexto, resultados = _wave(copia, formatos_compatibles, permitir_contexto=True)
    for resultado, item in zip(resultados, datos["resultados"]):
        mapa = _mapa(formatos, "wave-extension-captura-v2", resultado.identificador_origen)
        categoria = _texto(item, "categoria", "resultado WAVE")
        if categoria != mapa["categoria"]:
            _formato(f"categoría WAVE incoherente para {resultado.identificador_origen}")
        resultado.id_resultado = resultado.id_resultado.replace("captura-v1:", "captura-v2:")
        resultado.estado_original = categoria
        resultado.tipo_resultado = (TipoResultado.ALERTA if categoria == "alert" else
                                   TipoResultado.HALLAZGO if categoria in {"error", "contrast"} else
                                   TipoResultado.EVIDENCIA_CONTEXTUAL)
    return "wave-extension-captura-v2", datos["procedencia"], herramienta, version, fecha, contexto, resultados


def axe_ampliado(datos, formatos):
    nombre, procedencia, _, version, fecha, contexto, resultados = _axe(datos, formatos)
    fuera = []
    for grupo in ("passes", "inapplicable"):
        for indice, item in enumerate(datos[grupo]):
            ruta = f"/{grupo}/{indice}"
            item = _objeto(item, ruta)
            identificador = _texto(item, "id", ruta)
            if identificador not in formatos["axe-core-playwright"]:
                fuera.append({"identificadorOrigen": identificador, "rutaOrigen": ruta,
                              "motivo": "fuera_catalogo_admitido"})
                continue
            nodos = _lista(item.get("nodes"), f"{ruta}.nodes")
            if grupo == "passes" and not nodos:
                _insuficiente(f"{ruta}.nodes está vacío")
            for nodo in nodos:
                nodo = _objeto(nodo, ruta)
                objetivo = _lista(nodo.get("target"), f"{ruta}.target")
                if not _objetivo_axe(objetivo):
                    _insuficiente(f"{ruta}.target está vacío o es inválido")
            mapa = _mapa(formatos, nombre, identificador)
            resultado = _resultado(nombre, identificador, mapa, len(resultados), TipoResultado.AUDITORIA,
                                   item.get("impact"), grupo, contexto["url"],
                                   {"nodes": nodos, "impact": item.get("impact")}, item, ruta)
            resultados.append(resultado)
    contexto["reglasFueraCobertura"] = fuera
    return nombre, procedencia, Herramienta.AXE_CORE, version, fecha, contexto, resultados


def lighthouse_ampliado(datos, formatos):
    nombre, procedencia, herramienta, version, fecha, contexto, resultados = _lighthouse(datos, formatos)
    http = datos["audits"].get("http-status-code")
    if http is not None and (not isinstance(http, dict) or http.get("score") != 1 or isinstance(http.get("score"), bool)):
        _insuficiente("el documento principal no tiene una auditoría HTTP satisfactoria; no se clasifica como la vista esperada")
    referencias = set()
    for categoria in datos["categories"].values():
        categoria = _objeto(categoria, "categories")
        for ref in _lista(categoria.get("auditRefs"), "auditRefs"):
            referencias.add(_texto(_objeto(ref, "auditRef"), "id", "auditRef"))
    cobertura = {}
    for identificador in ("viewport", "paste-preventing-inputs", "errors-in-console"):
        mapa = _mapa(formatos, nombre, identificador)
        if identificador not in datos["audits"]:
            cobertura[identificador] = "ausente_en_reporte"
            continue
        if version not in mapa["versionesAdmitidas"]:
            raise ErrorImportacion("VERSION_NO_ADMITIDA", f"{identificador}: versión {version} sin contrato comprobado")
        if identificador not in referencias:
            _insuficiente(f"{identificador} no está referenciada por ninguna categoría")
        auditoria = _objeto(datos["audits"][identificador], identificador)
        if _texto(auditoria, "id", identificador) != identificador:
            _formato(f"id incoherente en {identificador}")
        modo = _texto(auditoria, "scoreDisplayMode", identificador)
        score = auditoria.get("score")
        if modo not in {"error", "notApplicable"}:
            if modo not in mapa["modosAdmitidos"]:
                _formato(f"modo {modo} no admitido para {identificador}")
            if isinstance(score, bool) or not isinstance(score, (int, float)) or score not in (0, 1):
                _formato(f"{identificador}.score debe ser 0 o 1 numérico")
            if score == 0 and identificador in {"paste-preventing-inputs", "errors-in-console"}:
                detalles = _objeto(auditoria.get("details"), f"{identificador}.details")
                elementos = _lista(detalles.get("items"), f"{identificador}.details.items")
                if not elementos:
                    _insuficiente(f"{identificador}: un fallo requiere evidencia de elementos o errores")
        resultados.append(_resultado(nombre, identificador, mapa, len(resultados), TipoResultado.AUDITORIA,
                                     score, modo, contexto["url"],
                                     {"details": auditoria.get("details"), "errorMessage": auditoria.get("errorMessage")},
                                     auditoria, f"/audits/{identificador}"))
        cobertura[identificador] = "presente"
    contexto["coberturaAuditoriasTecnicas"] = cobertura
    return nombre, procedencia, herramienta, version, fecha, contexto, resultados
