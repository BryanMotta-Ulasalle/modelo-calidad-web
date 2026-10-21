"""Contrato de la etapa entre el reporte fuente y ResultadoNormalizado."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from modelo_calidad_web.dominio.enumeraciones import DimensionId, Herramienta, TipoResultado


class ResultadoImportado(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id_resultado: str = Field(alias="idResultado")
    identificador_origen: str = Field(alias="identificadorOrigen")
    id_indicador: str = Field(alias="idIndicador")
    id_dimension: DimensionId = Field(alias="idDimension")
    referencia_tecnica: list[str] = Field(alias="referenciaTecnica")
    tipo_resultado: TipoResultado = Field(alias="tipoResultado")
    valor_original: Any = Field(alias="valorOriginal")
    unidad_original: str | None = Field(default=None, alias="unidadOriginal")
    ubicacion_elemento: str | None = Field(default=None, alias="ubicacionElemento")
    estado_original: str = Field(alias="estadoOriginal")
    estado_normalizado: None = Field(default=None, alias="estadoNormalizado")
    prioridad: None = None
    evidencia: Any = None
    ruta_origen: str = Field(alias="rutaOrigen")
    datos_originales: dict[str, Any] = Field(alias="datosOriginales")


class LoteImportado(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version_esquema: str = Field(default="0.2.0", alias="versionEsquema")
    formato_fuente: str = Field(alias="formatoFuente")
    procedencia: str
    herramienta: Herramienta
    version_herramienta: str = Field(alias="versionHerramienta")
    version_catalogo_mapeos: str = Field(alias="versionCatalogoMapeos")
    id_evaluacion: str = Field(alias="idEvaluacion")
    id_modulo_vista: str = Field(alias="idModuloVista")
    fecha_hora: datetime = Field(alias="fechaHora")
    contexto: dict[str, Any]
    resultados: list[ResultadoImportado]
    entrada_original: dict[str, Any] = Field(alias="entradaOriginal")
    texto_original: str = Field(alias="textoOriginal")
    sha256_original: str = Field(alias="sha256Original")
