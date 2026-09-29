from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enumeraciones import (
    DimensionId,
    EstadoNormalizado,
    Herramienta,
    Prioridad,
    TipoResultado,
)


class ResultadoNormalizado(BaseModel):
    """Unidad mínima de información definida por los campos CR-01 a CR-18."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
    )

    id_resultado: str | int = Field(alias="idResultado")  # CR-01
    id_evaluacion: str = Field(alias="idEvaluacion", min_length=1)  # CR-02
    id_modulo_vista: str = Field(alias="idModuloVista", min_length=1)  # CR-03
    herramienta: Herramienta  # CR-04
    version_herramienta: str = Field(alias="versionHerramienta", min_length=1)  # CR-05
    identificador_origen: str = Field(alias="identificadorOrigen", min_length=1)  # CR-06
    tipo_resultado: TipoResultado = Field(alias="tipoResultado")  # CR-07
    valor_original: str | bool | int | float = Field(alias="valorOriginal")  # CR-08
    unidad: str | None = None  # CR-09
    ubicacion_elemento: str | None = Field(default=None, alias="ubicacionElemento")  # CR-10
    id_indicador: str = Field(alias="idIndicador", pattern=r"^[APU]-\d{2}$")  # CR-11
    id_dimension: DimensionId = Field(alias="idDimension")  # CR-12
    referencia_tecnica: list[str] = Field(
        alias="referenciaTecnica", min_length=1
    )  # CR-13
    estado_original: str = Field(alias="estadoOriginal", min_length=1)  # CR-14
    estado_normalizado: EstadoNormalizado = Field(alias="estadoNormalizado")  # CR-15
    prioridad: Prioridad | None = None  # CR-16
    evidencia: str | dict[str, Any] | list[Any] | None = None  # CR-17
    fecha_hora: datetime = Field(alias="fechaHora")  # CR-18

    # Campo de implementación para cumplir RN-01: conserva el registro fuente.
    datos_originales: dict[str, Any] = Field(alias="datosOriginales")

    @field_validator("id_resultado")
    @classmethod
    def validar_id_resultado(cls, value: str | int) -> str | int:
        if isinstance(value, str) and not value.strip():
            raise ValueError("idResultado no puede estar vacío")
        return value

    @field_validator("unidad")
    @classmethod
    def validar_unidad_de_metrica(cls, value: str | None, info):
        tipo = info.data.get("tipo_resultado")
        if tipo == TipoResultado.METRICA and not value:
            raise ValueError("unidad es obligatoria para resultados de tipo metrica")
        return value

    @model_validator(mode="after")
    def validar_evidencia_de_hallazgos(self):
        if self.tipo_resultado in {TipoResultado.HALLAZGO, TipoResultado.ALERTA}:
            if self.evidencia in (None, "", [], {}):
                raise ValueError(
                    "evidencia es obligatoria para hallazgos y alertas"
                )
        return self

