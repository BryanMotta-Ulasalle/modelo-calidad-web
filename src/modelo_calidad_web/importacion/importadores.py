"""Lectores conservadores: mapean identidad, pero no calculan estados."""

import copy
import hashlib
import json
import math
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from modelo_calidad_web.dominio.enumeraciones import Herramienta, TipoResultado
from modelo_calidad_web.validacion.catalogos import cargar_catalogos

from .modelos import LoteImportado, ResultadoImportado


class ErrorImportacion(ValueError):
    """Error con categoría estable para la CLI y los consumidores."""

    def __init__(self, codigo: str, detalle: str):
        self.codigo = codigo
        super().__init__(detalle)


def _formato(detalle: str) -> None:
    raise ErrorImportacion("FORMATO", detalle)


def _insuficiente(detalle: str) -> None:
    raise ErrorImportacion("DATOS_INSUFICIENTES", detalle)


def _pares_json(pares):
    objeto = {}
    for clave, valor in pares:
        if clave in objeto:
            _formato(f"clave JSON repetida: {clave}")
        objeto[clave] = valor
    return objeto


def _objeto(valor: Any, lugar: str) -> dict[str, Any]:
    if valor is None:
        _insuficiente(f"falta {lugar}")
    if not isinstance(valor, dict):
        _formato(f"{lugar} debe ser un objeto JSON")
    return valor


def _lista(valor: Any, lugar: str) -> list[Any]:
    if valor is None:
        _insuficiente(f"falta {lugar}")
    if not isinstance(valor, list):
        _formato(f"{lugar} debe ser una lista JSON")
    return valor


def _texto(objeto: dict[str, Any], clave: str, lugar: str) -> str:
    if clave not in objeto or objeto[clave] is None or objeto[clave] == "":
        _insuficiente(f"falta {lugar}.{clave}")
    valor = objeto[clave]
    if not isinstance(valor, str):
        _formato(f"{lugar}.{clave} debe ser texto")
    if not valor.strip():
        _insuficiente(f"{lugar}.{clave} está vacío")
    return valor


def _fecha(objeto: dict[str, Any], clave: str, lugar: str) -> datetime:
    valor = _texto(objeto, clave, lugar)
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError as error:
        raise ErrorImportacion("FORMATO", f"{lugar}.{clave} no es una fecha ISO válida") from error
    if fecha.tzinfo is None:
        _insuficiente(f"{lugar}.{clave} debe indicar zona horaria")
    return fecha


def _mapeos(ruta: str | Path | None) -> tuple[str, dict[str, Any]]:
    ubicacion = Path(ruta) if ruta is not None else files("modelo_calidad_web").joinpath("catalogos/mapeos_fuentes_v1.json")
    try:
        with ubicacion.open("r", encoding="utf-8") as archivo:
            catalogo = json.load(archivo)
    except (OSError, json.JSONDecodeError) as error:
        raise ErrorImportacion("FORMATO", f"no se puede leer el catálogo de mapeos: {error}") from error
    _objeto(catalogo, "catálogo de mapeos")
    version = _texto(catalogo, "version", "catálogo de mapeos")
    formatos = _objeto(catalogo.get("mapeos"), "catálogo de mapeos.mapeos")
    if version == "2.0.0" and not {"wave-extension-captura-v1", "wave-extension-captura-v2", "axe-core-playwright", "lighthouse-result"}.issubset(formatos):
        _formato("el catálogo 2.0.0 carece de un formato requerido")
    try:
        catalogos = cargar_catalogos()
        for formato, entradas in formatos.items():
            for origen, mapa in _objeto(entradas, formato).items():
                _objeto(mapa, f"{formato}.{origen}")
                indicador = _texto(mapa, "indicador", f"{formato}.{origen}")
                dimension = _texto(mapa, "dimension", f"{formato}.{origen}")
                if indicador not in catalogos.indicadores or catalogos.indicadores[indicador]["dimension"] != dimension:
                    _formato(f"mapeo incoherente para {formato}.{origen}")
                referencias = _lista(mapa.get("referencias"), f"{formato}.{origen}.referencias")
                if not referencias or any(not isinstance(ref, str) or not ref.strip() for ref in referencias):
                    _formato(f"referencias inválidas para {formato}.{origen}")
                if catalogo["version"] == "2.0.0":
                    if formato == "wave-extension-captura-v2" and mapa.get("categoria") not in {"error", "contrast", "alert", "feature", "structure", "aria"}:
                        _formato(f"categoría WAVE inválida para {origen}")
                    if formato == "lighthouse-result" and origen in {"viewport", "paste-preventing-inputs", "errors-in-console"}:
                        for clave in ("versionesAdmitidas", "modosAdmitidos"):
                            valores = mapa.get(clave)
                            if not isinstance(valores, list) or not valores or any(not isinstance(v, str) or not v.strip() for v in valores):
                                _formato(f"{clave} inválido para {origen}")
    except (KeyError, TypeError, OSError, ValueError) as error:
        if isinstance(error, ErrorImportacion):
            raise
        raise ErrorImportacion("FORMATO", f"catálogo de mapeos inválido: {error}") from error
    return version, formatos


def _mapa(formatos: dict[str, Any], formato: str, identificador: str) -> dict[str, Any]:
    mapa = formatos.get(formato, {}).get(identificador)
    if mapa is None:
        raise ErrorImportacion("SIN_MAPEO", f"{formato}: identificador {identificador!r} sin mapeo")
    return mapa


def _resultado(
    formato: str, identificador: str, mapa: dict[str, Any], indice: int,
    tipo: TipoResultado, valor: Any, estado: str, ubicacion: str | None,
    evidencia: Any, original: dict[str, Any], ruta: str, unidad: str | None = None,
) -> ResultadoImportado:
    return ResultadoImportado(
        idResultado=f"{formato}:{identificador}:{indice}",
        identificadorOrigen=identificador,
        idIndicador=mapa["indicador"],
        idDimension=mapa["dimension"],
        referenciaTecnica=mapa["referencias"],
        tipoResultado=tipo,
        valorOriginal=valor,
        unidadOriginal=unidad,
        ubicacionElemento=ubicacion,
        estadoOriginal=estado,
        evidencia=copy.deepcopy(evidencia),
        rutaOrigen=ruta,
        datosOriginales=copy.deepcopy(original),
    )


def _wave(datos: dict[str, Any], formatos: dict[str, Any], *, permitir_contexto: bool = False):
    if datos.get("formato") != "wave-extension-captura-v1":
        _formato("formato WAVE no reconocido")
    if datos.get("procedencia") != "transcripcion_manual":
        _formato("WAVE debe declarar procedencia transcripcion_manual")
    captura = _objeto(datos.get("captura"), "captura")
    fecha = _fecha(captura, "fechaHora", "captura")
    version = _texto(captura, "versionExtension", "captura")
    url = _texto(captura, "url", "captura")
    contexto = _objeto(captura.get("contexto"), "captura.contexto")
    for clave in ("perfilAcceso", "dispositivo", "navegador"):
        _texto(contexto, clave, "captura.contexto")
    entradas = _lista(datos.get("resultados"), "resultados")
    if not entradas:
        _insuficiente("captura WAVE sin resultados")
    resultados = []
    for i, item in enumerate(entradas):
        lugar = f"resultados[{i}]"
        item = _objeto(item, lugar)
        identificador = _texto(item, "identificador", lugar)
        mapa = _mapa(formatos, "wave-extension-captura-v1", identificador)
        contextual = permitir_contexto and mapa.get("categoria") in {"feature", "structure", "aria"}
        if "valor" not in item or (item["valor"] is None and not contextual):
            _insuficiente(f"falta {lugar}.valor")
        ubicacion = _texto(item, "ubicacion", lugar)
        evidencia = _objeto(item.get("evidencia"), f"{lugar}.evidencia")
        _texto(evidencia, "observacion", f"{lugar}.evidencia")
        _texto(evidencia, "referenciaCaptura", f"{lugar}.evidencia")
        resultados.append(_resultado("wave-extension-captura-v1", identificador, mapa, i,
            TipoResultado.HALLAZGO, item["valor"], "transcrito", ubicacion,
            evidencia, item, f"/resultados/{i}"))
    return "wave-extension-captura-v1", "transcripcion_manual", Herramienta.WAVE, version, fecha, {"url": url, **copy.deepcopy(contexto)}, resultados


def _axe(datos: dict[str, Any], formatos: dict[str, Any]):
    fecha = _fecha(datos, "timestamp", "axe")
    url = _texto(datos, "url", "axe")
    engine = _objeto(datos.get("testEngine"), "testEngine")
    if _texto(engine, "name", "testEngine") != "axe-core":
        _formato("testEngine.name debe ser axe-core")
    version = _texto(engine, "version", "testEngine")
    runner = _objeto(datos.get("testRunner"), "testRunner")
    _texto(runner, "name", "testRunner")
    environment = _objeto(datos.get("testEnvironment"), "testEnvironment")
    grupos = {clave: _lista(datos.get(clave), clave) for clave in ("violations", "incomplete", "passes", "inapplicable")}
    resultados = []
    for grupo in ("violations", "incomplete"):
        for i, item in enumerate(grupos[grupo]):
            lugar = f"{grupo}[{i}]"
            item = _objeto(item, lugar)
            identificador = _texto(item, "id", lugar)
            mapa = _mapa(formatos, "axe-core-playwright", identificador)
            nodos = _lista(item.get("nodes"), f"{lugar}.nodes")
            if not nodos:
                _insuficiente(f"{lugar}.nodes está vacío")
            for j, nodo in enumerate(nodos):
                nodo = _objeto(nodo, f"{lugar}.nodes[{j}]")
                objetivo = _lista(nodo.get("target"), f"{lugar}.nodes[{j}].target")
                if not _objetivo_axe(objetivo):
                    _insuficiente(f"{lugar}.nodes[{j}].target está vacío")
            resultados.append(_resultado("axe-core-playwright", identificador, mapa, len(resultados),
                TipoResultado.HALLAZGO if grupo == "violations" else TipoResultado.ALERTA,
                item.get("impact"), grupo, url, {"nodes": copy.deepcopy(nodos), "impact": item.get("impact")},
                item, f"/{grupo}/{i}"))
    contexto = {"url": url, "testRunner": copy.deepcopy(runner), "testEnvironment": copy.deepcopy(environment), "testEngine": copy.deepcopy(engine), "toolOptions": copy.deepcopy(datos.get("toolOptions"))}
    return "axe-core-playwright", "axe_core_json", Herramienta.AXE, version, fecha, contexto, resultados


def _objetivo_axe(valor: Any) -> bool:
    """Admite las rutas anidadas de iframe/shadow DOM descritas por axe-core."""
    if isinstance(valor, str):
        return bool(valor.strip())
    return isinstance(valor, list) and bool(valor) and all(_objetivo_axe(v) for v in valor)


def _lighthouse(datos: dict[str, Any], formatos: dict[str, Any]):
    version = _texto(datos, "lighthouseVersion", "LHR")
    fecha = _fecha(datos, "fetchTime", "LHR")
    url = _texto(datos, "finalDisplayedUrl", "LHR")
    _texto(datos, "userAgent", "LHR")
    ajustes = _objeto(datos.get("configSettings"), "configSettings")
    auditorias = _objeto(datos.get("audits"), "audits")
    categorias = _objeto(datos.get("categories"), "categories")
    if datos.get("runtimeError"):
        _insuficiente("LHR contiene runtimeError; ejecución no utilizable")
    rendimiento = _objeto(categorias.get("performance"), "categories.performance")
    referencias = _lista(rendimiento.get("auditRefs"), "categories.performance.auditRefs")
    metricas = []
    for i, ref in enumerate(referencias):
        ref = _objeto(ref, f"auditRefs[{i}]")
        if ref.get("group") == "metrics":
            metricas.append(_texto(ref, "id", f"auditRefs[{i}]"))
    if not metricas:
        _insuficiente("LHR no contiene referencias de métricas de rendimiento")
    resultados = []
    for i, identificador in enumerate(metricas):
        mapa = _mapa(formatos, "lighthouse-result", identificador)
        auditoria = _objeto(auditorias.get(identificador), f"audits.{identificador}")
        if _texto(auditoria, "id", f"audits.{identificador}") != identificador:
            _formato(f"audits.{identificador}.id no coincide con la clave")
        valor = auditoria.get("numericValue")
        if valor is None:
            _insuficiente(f"audits.{identificador}.numericValue ausente")
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            _formato(f"audits.{identificador}.numericValue debe ser número finito")
        unidad = _texto(auditoria, "numericUnit", f"audits.{identificador}")
        if unidad not in mapa.get("unidadesOrigen", [mapa.get("unidadOrigen")]):
            _formato(f"audits.{identificador}.numericUnit no coincide con el catálogo")
        resultados.append(_resultado("lighthouse-result", identificador, mapa, i,
            TipoResultado.METRICA, valor, "numericValue", url,
            {"displayValue": auditoria.get("displayValue"), "warnings": auditoria.get("warnings")},
            auditoria, f"/audits/{identificador.replace('~', '~0').replace('/', '~1')}", unidad))
    contexto = {"url": url, "requestedUrl": datos.get("requestedUrl"), "userAgent": datos["userAgent"], "configSettings": copy.deepcopy(ajustes), "environment": copy.deepcopy(datos.get("environment"))}
    return "lighthouse-result", "lighthouse_result_json", Herramienta.LIGHTHOUSE, version, fecha, contexto, resultados


def importar_datos(datos: Any, formato: str, id_evaluacion: str, id_modulo_vista: str,
                   *, texto_original: str | None = None, catalogo_mapeos: str | Path | None = None,
                   ejecutor: str | None = None, perfil: str = "incremento-2") -> LoteImportado:
    """Importa un documento JSON completo sin mutarlo; nunca asigna estado ni prioridad."""
    if not isinstance(datos, dict):
        _formato("la entrada debe ser un objeto JSON")
    if not id_evaluacion.strip() or not id_modulo_vista.strip():
        _insuficiente("idEvaluacion e idModuloVista son obligatorios")
    if texto_original is None:
        try:
            texto_original = json.dumps(datos, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ErrorImportacion("FORMATO", f"datos no representables como JSON: {error}") from error
    else:
        try:
            reconstruido = json.loads(texto_original, object_pairs_hook=_pares_json,
                                       parse_constant=lambda valor: _formato(f"constante JSON no válida: {valor}"))
            json.dumps(reconstruido, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ErrorImportacion("FORMATO", f"textoOriginal no es JSON válido: {error}") from error
        if reconstruido != datos:
            _formato("textoOriginal no coincide con los datos de entrada")
    if perfil not in {"incremento-2", "incremento-3"}:
        _formato(f"perfil de importación no admitido: {perfil}")
    if perfil == "incremento-3" and catalogo_mapeos is None:
        catalogo_mapeos = files("modelo_calidad_web").joinpath("catalogos/mapeos_fuentes_v2.json")
    version_mapeos, formatos = _mapeos(catalogo_mapeos)
    lectores = {"wave-extension-captura-v1": _wave, "axe-core-playwright": _axe, "lighthouse-result": _lighthouse}
    if perfil == "incremento-3":
        from .ampliada import axe_ampliado, lighthouse_ampliado, wave_ampliado
        if version_mapeos != "2.0.0":
            _formato("incremento-3 requiere el catálogo de mapeos 2.0.0")
        lectores.update({"wave-extension-captura-v2": wave_ampliado,
                         "axe-core-playwright": axe_ampliado, "lighthouse-result": lighthouse_ampliado})
    if formato not in lectores:
        _formato(f"formato de entrada no soportado: {formato}")
    if formato == "axe-core-playwright" and ejecutor != "playwright":
        _insuficiente("se requiere declarar ejecutor=playwright para axe-core")
    nombre, procedencia, herramienta, version, fecha, contexto, resultados = lectores[formato](datos, formatos)
    if ejecutor is not None:
        contexto["ejecutorDeclarado"] = ejecutor
    return LoteImportado(
        versionEsquema="0.3.0" if perfil == "incremento-3" else "0.2.0",
        formatoFuente=nombre, procedencia=procedencia, herramienta=herramienta,
        versionHerramienta=version, versionCatalogoMapeos=version_mapeos,
        idEvaluacion=id_evaluacion, idModuloVista=id_modulo_vista, fechaHora=fecha,
        contexto=contexto, resultados=resultados, entradaOriginal=copy.deepcopy(datos),
        textoOriginal=texto_original, sha256Original=hashlib.sha256(texto_original.encode("utf-8")).hexdigest(),
    )


def importar_archivo(ruta: str | Path, formato: str, id_evaluacion: str, id_modulo_vista: str,
                    *, catalogo_mapeos: str | Path | None = None,
                    ejecutor: str | None = None,
                    manifiesto_procedimiento: str | Path | None = None,
                    perfil: str = "incremento-2") -> LoteImportado:
    try:
        texto = Path(ruta).read_bytes().decode("utf-8")
        datos = json.loads(texto, object_pairs_hook=_pares_json,
                           parse_constant=lambda valor: _formato(f"constante JSON no válida: {valor}"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ErrorImportacion("FORMATO", f"no se puede leer JSON UTF-8: {error}") from error
    lote = importar_datos(datos, formato, id_evaluacion, id_modulo_vista,
                          texto_original=texto, catalogo_mapeos=catalogo_mapeos, ejecutor=ejecutor, perfil=perfil)
    if manifiesto_procedimiento is not None:
        if formato != "axe-core-playwright":
            _formato("el manifiesto de procedimiento solo se admite para axe-core-playwright")
        try:
            bytes_manifiesto = Path(manifiesto_procedimiento).read_bytes()
            manifiesto = json.loads(bytes_manifiesto.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ErrorImportacion("FORMATO", f"manifiesto de procedimiento no legible: {error}") from error
        manifiesto = _objeto(manifiesto, "manifiesto de procedimiento")
        if manifiesto.get("sha256Fuente") != lote.sha256_original:
            _formato("sha256Fuente del manifiesto no coincide con el JSON importado")
        if manifiesto.get("urlFinal") != datos.get("url"):
            _formato("urlFinal del manifiesto no coincide con el JSON importado")
        if manifiesto.get("testEngine") != datos.get("testEngine"):
            _formato("testEngine del manifiesto no coincide con el JSON importado")
        _texto(manifiesto, "playwrightVersion", "manifiesto de procedimiento")
        _texto(manifiesto, "procedimiento", "manifiesto de procedimiento")
        lote.contexto["evidenciaEjecucion"] = {
            "tipo": "manifiesto_vinculado_por_sha256",
            "sha256Manifiesto": hashlib.sha256(bytes_manifiesto).hexdigest(),
            "manifiesto": copy.deepcopy(manifiesto),
        }
    return lote
