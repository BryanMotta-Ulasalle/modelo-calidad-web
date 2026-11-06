"""Contratos del manifiesto explícito y del diagnóstico del cuarto incremento."""

from datetime import datetime
from typing import Any, Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from modelo_calidad_web.dominio.enumeraciones import EstadoNormalizado, Prioridad
from modelo_calidad_web.procesamiento.modelos import LoteProcesado, Registro, RevisionRegistrada

Texto = Annotated[str, Field(min_length=1)]
Identificador = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
TextoIntegro = Annotated[str, StringConstraints(strip_whitespace=False)]


class FuenteDeclarada(Registro):
    id_fuente: Identificador
    ruta: Texto
    sha256: Hash


class ReferenciaObservacion(Registro):
    id_fuente: Identificador
    id_resultado: Texto
    indice_nodo: Annotated[int, Field(strict=True, ge=0)] | None = None


class Coincidencia(Registro):
    id_coincidencia: Identificador
    referencias: list[ReferenciaObservacion] = Field(min_length=2)
    elemento_canonico: Texto
    problema_comun: Texto
    responsable: Texto
    fecha_hora: datetime
    fundamento: Texto
    evidencia: Texto

    @field_validator("fecha_hora")
    @classmethod
    def zona(cls, valor):
        if valor.tzinfo is None:
            raise ValueError("la coincidencia documentada requiere zona horaria")
        return valor


class GrupoDeclarado(Registro):
    id_grupo: Identificador
    id_evaluacion: Texto
    inicio: datetime
    fin: datetime
    perfil_acceso: Texto
    perfil_rendimiento: Literal["mobile", "desktop"] | None
    condiciones_declaradas: dict[str, Any] = Field(min_length=1)
    justificacion_comparabilidad: Texto
    fuentes: list[FuenteDeclarada] = Field(min_length=1)
    coincidencias: list[Coincidencia] = Field(default_factory=list)

    @model_validator(mode="after")
    def intervalo(self):
        if self.inicio.tzinfo is None or self.fin.tzinfo is None:
            raise ValueError("el intervalo requiere zona horaria")
        if self.fin < self.inicio:
            raise ValueError("el fin no puede preceder al inicio")
        for campo in ("ventanaAncho", "ventanaAlto"):
            if campo in self.condiciones_declaradas:
                valor = self.condiciones_declaradas[campo]
                if type(valor) is not int or valor <= 0:
                    raise ValueError(f"condición de ventana inválida: {campo}")
        return self


class VistaDeclarada(Registro):
    id_modulo_vista: Texto
    nombre: Texto
    url: Texto
    grupos: list[GrupoDeclarado]  # Vacío: vista seleccionada aún sin evidencia.


class ComparacionDeclarada(Registro):
    id_comparacion: Identificador
    grupos: list[Identificador] = Field(min_length=2)
    protocolo: Texto
    responsable: Texto
    fecha_hora: datetime
    condiciones_comunes: dict[str, Any] = Field(min_length=1)
    max_diferencia_segundos: Annotated[int, Field(strict=True, gt=0)]

    @model_validator(mode="after")
    def validar(self):
        if self.fecha_hora.tzinfo is None or len(set(self.grupos)) != len(self.grupos):
            raise ValueError("comparación requiere fecha con zona y grupos diferentes")
        requeridas = {"navegador", "red", "cpu", "ventanaAncho", "ventanaAlto"}
        if not requeridas <= self.condiciones_comunes.keys():
            raise ValueError("comparación requiere navegador, red, CPU y ventana")
        for clave in ("navegador", "red", "cpu"):
            if not isinstance(self.condiciones_comunes[clave], str) or not self.condiciones_comunes[clave].strip():
                raise ValueError(f"condición común insuficiente: {clave}")
        for clave in ("ventanaAncho", "ventanaAlto"):
            valor = self.condiciones_comunes[clave]
            if type(valor) is not int or valor <= 0:
                raise ValueError(f"dimensión de ventana inválida: {clave}")
        return self


class ManifiestoDiagnostico(Registro):
    version_esquema: Literal["0.4.0", "0.4.1"] = "0.4.1"
    id_caso: Texto
    titulo: Texto
    tipo_datos: Literal["simulados", "publicos", "institucionales"]
    alcance: Texto
    vistas: list[VistaDeclarada] = Field(min_length=1)
    comparaciones: list[ComparacionDeclarada] = Field(default_factory=list)

    @model_validator(mode="after")
    def identificadores_unicos(self):
        def unicos(valores, clase):
            if len(valores) != len(set(valores)):
                raise ValueError(f"identificador de {clase} repetido")
        unicos([v.id_modulo_vista for v in self.vistas], "vista")
        grupos = [g for v in self.vistas for g in v.grupos]
        unicos([g.id_grupo for g in grupos], "grupo")
        unicos([f.id_fuente for g in grupos for f in g.fuentes], "fuente")
        unicos([c.id_coincidencia for g in grupos for c in g.coincidencias], "coincidencia")
        unicos([c.id_comparacion for c in self.comparaciones], "comparación")
        return self


class FuenteConservada(Registro):
    id_fuente: str
    ruta_declarada: str
    sha256: Hash
    texto_original: TextoIntegro
    lote: LoteProcesado
    verificacion_hash_intermedio: str = "pendiente"


class Observacion(Registro):
    id_observacion: str
    referencia: ReferenciaObservacion
    id_indicador: str
    id_dimension: str
    ubicacion: Any
    ruta_evidencia: str
    estado_automatico: EstadoNormalizado | None
    estado_vigente: EstadoNormalizado | None
    prioridad_automatica: Prioridad | None
    revision_vigente: RevisionRegistrada | None
    pendiente_revision: bool


class Hallazgo(Registro):
    id_hallazgo: str
    id_indicador: str
    estado: Literal["desfavorable", "requiere_revision", "intermedio"]
    ids_observaciones: list[str] = Field(min_length=1)
    id_coincidencia: str | None = None
    prioridades_observadas: list[str]
    motivo_agrupacion: str


class IndicadorIntegrado(Registro):
    id_indicador: str
    nombre: str
    situacion: Literal["con_observaciones", "sin_observaciones", "contextual"]
    estados_observados: dict[str, int]
    resultados_fuente: int
    ids_observaciones: list[str]
    ids_hallazgos: list[str]
    cobertura_por_fuente: dict[str, Any]
    metricas: list[dict[str, Any]]
    contexto: list[dict[str, Any]]
    limitacion: str
    alcance_tecnico: dict[str, Any] = Field(default_factory=dict)


class DimensionIntegrada(Registro):
    id_dimension: str
    nombre: str
    indicadores: list[IndicadorIntegrado]
    estados_observados: dict[str, int]
    hallazgos: int


class GrupoIntegrado(Registro):
    id_grupo: str
    fuentes: list[str]
    observaciones: list[Observacion]
    hallazgos: list[Hallazgo]
    dimensiones: list[DimensionIntegrada]


class VistaIntegrada(Registro):
    id_modulo_vista: str
    nombre: str
    url: str
    grupos: list[GrupoIntegrado]


class Recomendacion(Registro):
    id_recomendacion: str
    id_modulo_vista: str
    id_grupo: str
    id_hallazgo: str
    id_indicador: str
    tipo: Literal["correccion_a_verificar", "revision", "mejora_a_verificar"]
    accion: str
    ids_observaciones: list[str] = Field(min_length=1)
    referencias: list[str] = Field(min_length=1)
    prioridades_observadas: list[str]
    orden_tecnico: int
    justificacion: str
    elementos_afectados_minimos: int = 0
    elementos_observados_maximos: int = 0
    vistas_con_misma_comprobacion: int = 1
    casos_revision_asociados: int = 0
    criterio_desempate: str = ""


class Diagnostico(Registro):
    version_esquema: Literal["0.4.1"] = "0.4.1"
    version_integrador: Literal["0.4.1"] = "0.4.1"
    version_reglas_integracion: str
    sha256_reglas_integracion: Hash
    sha256_catalogo_alcance: Hash
    fecha_generacion: datetime
    sha256_manifiesto: Hash
    texto_manifiesto: TextoIntegro
    manifiesto: ManifiestoDiagnostico
    fuentes: list[FuenteConservada]
    vistas: list[VistaIntegrada]
    resumen_entre_vistas: list[dict[str, Any]]
    recomendaciones: list[Recomendacion]
    comparaciones: list[dict[str, Any]] = Field(default_factory=list)
    limitaciones: list[str]

