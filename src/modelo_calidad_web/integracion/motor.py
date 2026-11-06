"""Integra lotes verificados por contexto, conservando cada origen y decisión."""

import hashlib
import json
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from pydantic import ValidationError

from modelo_calidad_web.procesamiento.modelos import LoteProcesado
from modelo_calidad_web.procesamiento.motor import ErrorProcesamiento, json_estricto, leer_json
from modelo_calidad_web.procesamiento.revision import (
    validar_lote_procesado, revision_vigente, comprobar_hash_intermedio,
)
from modelo_calidad_web.validacion.catalogos import cargar_catalogos

from .modelos import (
    Diagnostico, DimensionIntegrada, FuenteConservada, GrupoIntegrado, Hallazgo,
    IndicadorIntegrado, ManifiestoDiagnostico, Observacion, Recomendacion,
    ReferenciaObservacion, VistaIntegrada,
)
from .comparacion import comparar, priorizar


def _hash(contenido):
    return hashlib.sha256(contenido).hexdigest()


def _clave(ref):
    return ref.id_fuente, ref.id_resultado, ref.indice_nodo


def _fallar(codigo, detalle):
    raise ErrorProcesamiento(codigo, detalle)


def _reglas():
    contenido = files("modelo_calidad_web").joinpath("catalogos/reglas_integracion_v2.json").read_bytes()
    return json_estricto(contenido.decode("utf-8")), _hash(contenido)


def _ventana_observada(lote):
    contexto = lote.entrada_importada.contexto
    entorno = contexto.get("testEnvironment", {}) if lote.motor_fuente == "axe-core" else {}
    if lote.motor_fuente == "Lighthouse":
        emulacion = contexto["configSettings"].get("screenEmulation", {})
        if not isinstance(emulacion, dict):
            _fallar("FORMATO", "screenEmulation debe ser un objeto")
        if not emulacion.get("disabled", False):
            entorno = {"windowWidth": emulacion.get("width"), "windowHeight": emulacion.get("height")}
    salida = {}
    for nombre, campo in (("ventanaAncho", "windowWidth"), ("ventanaAlto", "windowHeight")):
        valor = entorno.get(campo)
        if valor is not None:
            if type(valor) is not int or valor <= 0:
                _fallar("FORMATO", "dimensión observada de ventana inválida")
            salida[nombre] = valor
    return salida


def _comprobar_fuente(fuente, declarada, vista, grupo):
    if (fuente.id_fuente != declarada.id_fuente or fuente.ruta_declarada != declarada.ruta
            or fuente.sha256 != declarada.sha256
            or _hash(fuente.texto_original.encode("utf-8")) != declarada.sha256):
        _fallar("INTEGRIDAD", "el archivo clasificado no coincide con su referencia")
    original = LoteProcesado.model_validate(json_estricto(fuente.texto_original))
    if original != fuente.lote:
        _fallar("INTEGRIDAD", "el lote embebido difiere del archivo clasificado conservado")
    lote = fuente.lote
    validar_lote_procesado(lote)
    fuente.verificacion_hash_intermedio = comprobar_hash_intermedio(lote)
    entrada = lote.entrada_importada
    if lote.motor_fuente == "WAVE Extension":
        url_original = entrada.entrada_original["captura"]["url"]
    elif lote.motor_fuente == "axe-core":
        url_original = entrada.entrada_original["url"]
    else:
        url_original = entrada.entrada_original["finalDisplayedUrl"]
    if (entrada.id_modulo_vista != vista.id_modulo_vista
            or entrada.id_evaluacion != grupo.id_evaluacion
            or entrada.contexto.get("url") != vista.url or url_original != vista.url):
        _fallar("CONTEXTO_INCOMPATIBLE", "vista, evaluación o URL no corresponden al manifiesto")
    if entrada.fecha_hora.tzinfo is None or not grupo.inicio <= entrada.fecha_hora <= grupo.fin:
        _fallar("CONTEXTO_INCOMPATIBLE", "captura fuera del intervalo con zona declarado")
    contexto = entrada.contexto
    acceso = contexto.get("perfilAcceso")
    if acceso is not None and acceso != grupo.perfil_acceso:
        _fallar("CONTEXTO_INCOMPATIBLE", "perfil de acceso distinto del declarado")
    perfil = (contexto["configSettings"].get("formFactor")
              if entrada.formato_fuente == "lighthouse-result" else None)
    dispositivo_original = contexto.get("dispositivo")
    dispositivo = ({"escritorio": "desktop", "movil": "mobile", "móvil": "mobile",
                    "mobile": "mobile", "desktop": "desktop"}.get(dispositivo_original)
                   if isinstance(dispositivo_original, str) else None)
    if any(p is not None and p != grupo.perfil_rendimiento for p in (perfil, dispositivo)):
        _fallar("CONTEXTO_INCOMPATIBLE", "perfil de dispositivo distinto del declarado")
    # Solo se contrastan condiciones observables presentes; lo demás es declaración.
    for declaracion, valor in _ventana_observada(lote).items():
        if declaracion in grupo.condiciones_declaradas:
            if grupo.condiciones_declaradas[declaracion] != valor:
                _fallar("CONTEXTO_INCOMPATIBLE", f"{declaracion} no coincide con la fuente")


def _observaciones(fuente, numero_inicial):
    lote = fuente.lote
    salida = []
    for resultado in lote.resultados:
        origen, decision = resultado.origen, resultado.decision
        nodos = origen.datos_originales.get("nodes", []) if lote.motor_fuente == "axe-core" else []
        unidades = [(i, nodo["target"]) for i, nodo in enumerate(nodos)] if nodos else [
            (None, origen.ubicacion_elemento)]
        for indice, ubicacion in unidades:
            revision = revision_vigente(lote, origen.id_resultado, indice)
            estado = revision.registro.estado_revisado if revision else decision.estado_normalizado
            salida.append(Observacion(
                id_observacion=f"O-{numero_inicial + len(salida):06d}",
                referencia=ReferenciaObservacion(id_fuente=fuente.id_fuente,
                                                 id_resultado=origen.id_resultado, indice_nodo=indice),
                id_indicador=origen.id_indicador, id_dimension=origen.id_dimension.value,
                ubicacion=ubicacion,
                ruta_evidencia=origen.ruta_origen + (f"/nodes/{indice}" if indice is not None else ""),
                estado_automatico=decision.estado_normalizado, estado_vigente=estado,
                prioridad_automatica=decision.prioridad, revision_vigente=revision,
                pendiente_revision=estado == "requiere_revision",
            ))
    return salida


def _hallazgos(grupo, observaciones, fuentes, numero_inicial):
    por_ref = {_clave(o.referencia): o for o in observaciones}
    por_fuente = {f.id_fuente: f for f in fuentes}
    usados = set()
    grupos = []
    for coincidencia in grupo.coincidencias:
        miembros = []
        for ref in coincidencia.referencias:
            clave = _clave(ref)
            if clave not in por_ref or clave in usados:
                _fallar("COINCIDENCIA_INVALIDA", "referencia inexistente, repetida o usada en otra coincidencia")
            usados.add(clave)
            miembros.append(por_ref[clave])
        if (len({o.id_indicador for o in miembros}) != 1
                or any(o.estado_vigente != "desfavorable" for o in miembros)
                or any(o.id_dimension == "D-RE" for o in miembros)
                or any(not o.ubicacion for o in miembros)
                or len({por_fuente[o.referencia.id_fuente].lote.motor_fuente for o in miembros}) < 2):
            _fallar("COINCIDENCIA_INVALIDA",
                    "se requieren fallos no métricos del mismo indicador y herramientas distintas")
        # Una observación axe sin nodo no identifica un elemento concreto.
        if any(por_fuente[o.referencia.id_fuente].lote.motor_fuente == "axe-core"
               and o.referencia.indice_nodo is None for o in miembros):
            _fallar("COINCIDENCIA_INVALIDA", "la coincidencia axe requiere un nodo concreto")
        grupos.append((miembros, coincidencia.id_coincidencia,
                       "coincidencia_documentada_sin_inferencia_automatica"))
    for observacion in observaciones:
        if (_clave(observacion.referencia) not in usados
                and observacion.estado_vigente in {"desfavorable", "requiere_revision", "intermedio"}):
            grupos.append(([observacion], None, "observacion_individual_sin_equivalencia_confirmada"))
    return [
        Hallazgo(id_hallazgo=f"H-{numero_inicial + i:06d}", id_indicador=miembros[0].id_indicador,
                 estado=miembros[0].estado_vigente,
                 ids_observaciones=[o.id_observacion for o in miembros],
                 id_coincidencia=id_coincidencia,
                 prioridades_observadas=sorted({o.prioridad_automatica.value for o in miembros
                                                if o.prioridad_automatica is not None}),
                 motivo_agrupacion=motivo)
        for i, (miembros, id_coincidencia, motivo) in enumerate(grupos)
    ]


def _estados(observaciones):
    conteos = {e: 0 for e in ("favorable", "intermedio", "desfavorable", "requiere_revision",
                              "no_evaluado", "contextual_sin_estado")}
    for o in observaciones:
        conteos[o.estado_vigente.value if o.estado_vigente is not None else "contextual_sin_estado"] += 1
    return conteos


def _dimensiones(observaciones, hallazgos, fuentes, catalogos, alcances):
    dimensiones = []
    for id_dimension, dimension in catalogos.dimensiones.items():
        indicadores = []
        for id_indicador, indicador in catalogos.indicadores.items():
            if indicador["dimension"] != id_dimension:
                continue
            miembros = [o for o in observaciones if o.id_indicador == id_indicador]
            cobertura = {
                f.id_fuente: c.model_dump(mode="json", by_alias=True)
                for f in fuentes for c in f.lote.cobertura_indicadores if c.id_indicador == id_indicador
            }
            metricas, contexto = [], []
            for fuente in fuentes:
                for r in fuente.lote.resultados:
                    if r.origen.id_indicador == id_indicador and id_dimension == "D-RE":
                        metricas.append({
                            "idFuente": fuente.id_fuente, "idResultado": r.origen.id_resultado,
                            "valorOriginal": r.origen.valor_original, "unidadOriginal": r.origen.unidad_original,
                            "valorNormalizado": r.decision.valor_normalizado,
                            "unidadNormalizada": r.decision.unidad_normalizada,
                            "estado": r.decision.estado_normalizado, "condiciones": r.decision.condiciones,
                        })
                if id_indicador == "P-06" and fuente.lote.contexto_adicional:
                    contexto.append({"idFuente": fuente.id_fuente, **fuente.lote.contexto_adicional})
            contextual = bool(indicador.get("contextual"))
            indicadores.append(IndicadorIntegrado(
                id_indicador=id_indicador, nombre=indicador["nombre"],
                situacion="contextual" if contextual else "con_observaciones" if miembros else "sin_observaciones",
                estados_observados=_estados(miembros),
                resultados_fuente=len({_clave(o.referencia)[:2] for o in miembros}),
                ids_observaciones=[o.id_observacion for o in miembros],
                ids_hallazgos=[h.id_hallazgo for h in hallazgos if h.id_indicador == id_indicador],
                cobertura_por_fuente=cobertura, metricas=metricas, contexto=contexto,
                limitacion=alcances[id_indicador]["limite"], alcance_tecnico=alcances[id_indicador],
            ))
        dimensiones.append(DimensionIntegrada(
            id_dimension=id_dimension, nombre=dimension["nombre"], indicadores=indicadores,
            estados_observados=_estados([o for o in observaciones if o.id_dimension == id_dimension]),
            hallazgos=sum(h.id_indicador in {i.id_indicador for i in indicadores} for h in hallazgos),
        ))
    return dimensiones


def _recomendar(vista, grupo, hallazgos, observaciones, fuentes, reglas):
    por_id = {o.id_observacion: o for o in observaciones}
    resultados = {(f.id_fuente, r.origen.id_resultado): r for f in fuentes for r in f.lote.resultados}
    salida = []
    for h in hallazgos:
        miembros = [por_id[i] for i in h.ids_observaciones]
        if h.estado == "requiere_revision":
            tipo, accion, orden = ("revision",
                "Revisar la evidencia y documentar alcance, impacto y decisión antes de confirmar una corrección.",
                5)
        else:
            tipo = "mejora_a_verificar" if h.estado == "intermedio" else "correccion_a_verificar"
            accion = reglas["acciones"][h.id_indicador]
            tecnicas = [reglas["ordenTecnico"].index(p) for p in h.prioridades_observadas
                        if p in {"critica", "alta", "media", "baja"}]
            orden = 6 if h.estado == "intermedio" else min(tecnicas, default=4)
        referencias = set()
        for o in miembros:
            r = resultados[(o.referencia.id_fuente, o.referencia.id_resultado)]
            referencias.update(r.origen.referencia_tecnica)
            referencias.update(r.decision.referencias)
        salida.append(Recomendacion(
            id_recomendacion="R-" + h.id_hallazgo[2:], id_modulo_vista=vista.id_modulo_vista,
            id_grupo=grupo.id_grupo, id_hallazgo=h.id_hallazgo, id_indicador=h.id_indicador,
            tipo=tipo, accion=accion, ids_observaciones=h.ids_observaciones,
            referencias=sorted(referencias), prioridades_observadas=h.prioridades_observadas,
            orden_tecnico=orden,
            justificacion="Acción del catálogo para el estado vigente y la evidencia vinculada; "
                          "orden técnico del modelo, sin estimación de riesgo institucional.",
        ))
    return salida


def construir_diagnostico(manifiesto, texto_manifiesto, fuentes):
    """Función común para crear la salida y verificarla desde sus entradas embebidas."""
    fuentes = [f.model_copy(deep=True) for f in fuentes]
    if ManifiestoDiagnostico.model_validate(json_estricto(texto_manifiesto)) != manifiesto:
        _fallar("INTEGRIDAD", "manifiesto embebido diferente del texto original")
    reglas, hash_reglas = _reglas()
    catalogos = cargar_catalogos()
    contenido_alcance = files("modelo_calidad_web").joinpath("catalogos/alcance_indicadores_v1.json").read_bytes()
    alcances = {i["id"]: i for i in json_estricto(contenido_alcance.decode("utf-8"))["indicadores"]}
    if set(alcances) != set(catalogos.indicadores):
        _fallar("FORMATO", "catálogo de alcance incompleto")
    esperadas = [f.id_fuente for v in manifiesto.vistas for g in v.grupos for f in g.fuentes]
    if [f.id_fuente for f in fuentes] != esperadas:
        _fallar("INTEGRIDAD", "las fuentes no corresponden al manifiesto en su orden declarado")
    por_fuente = {f.id_fuente: f for f in fuentes}
    vistos_archivos, vistas_capturas = set(), set()
    vistas, recomendaciones, resumen = [], [], []
    numero_o, numero_h = 1, 1
    for vista in manifiesto.vistas:
        grupos = []
        for grupo in vista.grupos:
            entradas = [por_fuente[f.id_fuente] for f in grupo.fuentes]
            ventanas = {}
            for declarada, fuente in zip(grupo.fuentes, entradas):
                _comprobar_fuente(fuente, declarada, vista, grupo)
                for campo, valor in _ventana_observada(fuente.lote).items():
                    if campo in ventanas and ventanas[campo] != valor:
                        _fallar("CONTEXTO_INCOMPATIBLE", "ventanas observadas incompatibles en un mismo grupo")
                    ventanas[campo] = valor
                canonico = json.dumps(fuente.lote.entrada_importada.entrada_original,
                                      ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                clave = (fuente.lote.motor_fuente, _hash(canonico.encode("utf-8")))
                if fuente.sha256 in vistos_archivos or clave in vistas_capturas:
                    _fallar("FUENTE_REPETIDA", "un archivo o captura está incluido más de una vez")
                vistos_archivos.add(fuente.sha256)
                vistas_capturas.add(clave)
            observaciones = []
            for fuente in entradas:
                nuevas = _observaciones(fuente, numero_o)
                observaciones.extend(nuevas)
                numero_o += len(nuevas)
            hallazgos = _hallazgos(grupo, observaciones, entradas, numero_h)
            numero_h += len(hallazgos)
            dimensiones = _dimensiones(observaciones, hallazgos, entradas, catalogos, alcances)
            grupos.append(GrupoIntegrado(id_grupo=grupo.id_grupo, fuentes=[f.id_fuente for f in entradas],
                                         observaciones=observaciones, hallazgos=hallazgos, dimensiones=dimensiones))
            recomendaciones.extend(_recomendar(vista, grupo, hallazgos, observaciones, entradas, reglas))
            resumen.append({
                "idModuloVista": vista.id_modulo_vista, "idGrupo": grupo.id_grupo,
                "comparabilidadEntreVistas": "no_establecida_sin_protocolo_adicional",
                "dimensiones": {d.id_dimension: {
                    "estadosObservados": d.estados_observados, "hallazgos": d.hallazgos,
                    "indicadoresConObservaciones": [i.id_indicador for i in d.indicadores if i.ids_observaciones],
                    "indicadoresSinObservaciones": [i.id_indicador for i in d.indicadores
                                                    if i.situacion == "sin_observaciones"],
                } for d in dimensiones},
            })
        vistas.append(VistaIntegrada(id_modulo_vista=vista.id_modulo_vista, nombre=vista.nombre,
                                     url=vista.url, grupos=grupos))
        if not grupos:
            resumen.append({"idModuloVista": vista.id_modulo_vista, "idGrupo": None,
                            "situacion": "sin_fuentes", "dimensionesSinDatos": list(catalogos.dimensiones)})
    comparaciones = comparar(manifiesto, vistas, fuentes)
    priorizar(recomendaciones, vistas, fuentes, comparaciones)
    return Diagnostico(
        version_reglas_integracion=reglas["version"], sha256_reglas_integracion=hash_reglas,
        sha256_catalogo_alcance=_hash(contenido_alcance),
        fecha_generacion=datetime.now(timezone.utc), sha256_manifiesto=_hash(texto_manifiesto.encode("utf-8")),
        texto_manifiesto=texto_manifiesto, manifiesto=manifiesto, fuentes=fuentes, vistas=vistas,
        resumen_entre_vistas=resumen, recomendaciones=recomendaciones, comparaciones=comparaciones,
        limitaciones=reglas["limitaciones"],
    )


def diagnosticar_archivo(ruta):
    contenido, datos = leer_json(ruta)
    try:
        manifiesto = ManifiestoDiagnostico.model_validate(datos)
        fuentes = []
        for vista in manifiesto.vistas:
            for grupo in vista.grupos:
                for declarada in grupo.fuentes:
                    archivo = Path(declarada.ruta)
                    if not archivo.is_absolute():
                        archivo = Path(ruta).resolve().parent / archivo
                    fuente_bytes, fuente_datos = leer_json(archivo)
                    fuentes.append(FuenteConservada(
                        id_fuente=declarada.id_fuente, ruta_declarada=declarada.ruta,
                        sha256=_hash(fuente_bytes), texto_original=fuente_bytes.decode("utf-8"),
                        lote=LoteProcesado.model_validate(fuente_datos),
                    ))
        return construir_diagnostico(manifiesto, contenido.decode("utf-8"), fuentes)
    except ValidationError as error:
        raise ErrorProcesamiento("FORMATO", f"manifiesto o lote inválidos: {error}") from error


def verificar_diagnostico_archivo(ruta):
    """Recalcula la integración; no necesita acceder a las rutas originales."""
    _, datos = leer_json(ruta)
    if isinstance(datos, dict) and datos.get("versionEsquema") == "0.4.0":
        _fallar("VERSION_NO_ADMITIDA", "diagnóstico 0.4.0 histórico: vuelva a ejecutar diagnosticar "
                "con su manifiesto y salida nueva para aplicar las correcciones 0.4.1")
    try:
        diagnostico = Diagnostico.model_validate(datos)
        esperado = construir_diagnostico(
            diagnostico.manifiesto, diagnostico.texto_manifiesto, diagnostico.fuentes)
        recibido = diagnostico.model_dump(mode="json")
        comparado = esperado.model_dump(mode="json")
        recibido.pop("fecha_generacion")
        comparado.pop("fecha_generacion")
        if recibido != comparado:
            _fallar("INTEGRIDAD", "diagnóstico, recomendaciones o resúmenes alterados")
        return diagnostico
    except ValidationError as error:
        raise ErrorProcesamiento("FORMATO", f"diagnóstico inválido: {error}") from error

