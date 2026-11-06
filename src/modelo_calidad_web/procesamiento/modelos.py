"""Salida nueva: conserva el lote importado y añade decisiones explicables.

No se cambia ResultadoNormalizado de 0.1 para simular valores de impacto ausentes.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from pydantic.alias_generators import to_camel

from modelo_calidad_web.dominio.enumeraciones import EstadoNormalizado, Prioridad
from modelo_calidad_web.importacion.modelos import LoteImportado, ResultadoImportado


class Registro(BaseModel):
    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, alias_generator=to_camel,
        allow_inf_nan=False, str_strip_whitespace=True,
    )


class Decision(Registro):
    id_regla: str
    version_reglas: str
    referencias: list[str] = Field(min_length=1)
    estado_normalizado: EstadoNormalizado | None
    prioridad: Prioridad | None = None
    motivo_estado: str = Field(min_length=1)
    motivo_prioridad: str = Field(min_length=1)
    valor_normalizado: float | None = None
    unidad_normalizada: str | None = None
    condiciones: dict[str, Any] = Field(default_factory=dict)
    revision: Literal["pendiente", "no_requerida"]


class ResultadoProcesado(Registro):
    origen: ResultadoImportado
    etapa_origen: Literal["lote_importado", "fuente_conservada"]
    decision: Decision


class CoberturaFuente(Registro):
    identificador_origen: str
    ruta_origen: str
    motivo: Literal["fuera_catalogo_admitido"]


class CoberturaIndicador(Registro):
    id_indicador: str
    situacion: Literal["con_resultados", "sin_resultados_en_fuente", "fuera_del_formato", "contextual"]
    resultados_observados: int = Field(ge=0)
    identificadores_admitidos: list[str]
    motivo: str


class RevisionHumana(Registro):
    id_resultado: str = Field(min_length=1)
    responsable: str = Field(min_length=1)
    fecha_hora: datetime
    estado_revisado: EstadoNormalizado
    fundamento: str = Field(min_length=1)
    evidencia: str = Field(min_length=1)
    alcance: Literal["resultado_completo", "nodo"] | None = None
    indice_nodo: Annotated[int, Field(strict=True, ge=0)] | None = None

    @model_validator(mode="after")
    def alcance_coherente(self):
        if (self.alcance == "nodo") != (self.indice_nodo is not None):
            raise ValueError("alcance nodo requiere indiceNodo; resultado completo no admite índice")
        return self

    @field_validator("fecha_hora")
    @classmethod
    def exigir_zona(cls, fecha):
        if fecha.tzinfo is None:
            raise ValueError("la revisión requiere zona horaria")
        return fecha


class RevisionRegistrada(Registro):
    numero: int = Field(ge=1)
    situacion: Literal["realizada"] = "realizada"
    sha256_lote_previo: str = Field(pattern=r"^[0-9a-f]{64}$")
    registro: RevisionHumana
    decision_automatica: Decision


class LoteProcesado(Registro):
    version_esquema: Literal["0.3.0"] = "0.3.0"
    version_motor: Literal["0.3.0"] = "0.3.0"
    version_reglas: str
    sha256_reglas: str = Field(pattern=r"^[0-9a-f]{64}$")
    sha256_catalogo_mapeos: str = Field(pattern=r"^[0-9a-f]{64}$")
    sha256_lote_importado: str = Field(pattern=r"^[0-9a-f]{64}$")
    tipo_hash_entrada: Literal["archivo", "representacion_json"]
    texto_lote_importado: Annotated[str, StringConstraints(strip_whitespace=False)] | None = None
    fecha_procesamiento: datetime
    motor_fuente: str
    entrada_importada: LoteImportado
    resultados: list[ResultadoProcesado]
    fuentes_fuera_cobertura: list[CoberturaFuente] = Field(default_factory=list)
    cobertura_indicadores: list[CoberturaIndicador]
    contexto_adicional: dict[str, Any] = Field(default_factory=dict)
    limitaciones: list[str]
    historial_revisiones: list[RevisionRegistrada] = Field(default_factory=list)

    @model_validator(mode="after")
    def comprobar_contexto_y_resultados(self):
        ids = [r.origen.id_resultado for r in self.resultados]
        if len(ids) != len(set(ids)):
            raise ValueError("los resultados procesados requieren IDs únicos")
        for resultado in self.resultados:
            contextual = resultado.origen.tipo_resultado.value == "evidencia_contextual"
            if contextual != (resultado.decision.estado_normalizado is None):
                raise ValueError("solo la evidencia contextual carece de estado normalizado")
        return self
