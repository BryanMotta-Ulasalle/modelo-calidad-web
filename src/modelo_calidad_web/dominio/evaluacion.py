from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .resultado import ResultadoNormalizado


class ContextoEjecucion(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    perfil_acceso: str = Field(alias="perfilAcceso", min_length=1)
    dispositivo: str = Field(min_length=1)
    navegador: str = Field(min_length=1)
    red: str | None = None
    configuracion: dict[str, Any] = Field(default_factory=dict)


class Evaluacion(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id_evaluacion: str = Field(alias="idEvaluacion", min_length=1)
    id_modulo_vista: str = Field(alias="idModuloVista", min_length=1)
    fecha_inicio: datetime = Field(alias="fechaInicio")
    contexto: ContextoEjecucion
    resultados: list[ResultadoNormalizado] = Field(default_factory=list)

