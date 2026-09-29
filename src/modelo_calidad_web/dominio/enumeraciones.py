from enum import StrEnum


class Herramienta(StrEnum):
    WAVE = "WAVE"
    AXE = "axe DevTools"
    LIGHTHOUSE = "Lighthouse"


class TipoResultado(StrEnum):
    METRICA = "metrica"
    HALLAZGO = "hallazgo"
    AUDITORIA = "auditoria"
    ALERTA = "alerta"
    EVIDENCIA_CONTEXTUAL = "evidencia_contextual"


class DimensionId(StrEnum):
    ACCESIBILIDAD = "D-AC"
    RENDIMIENTO = "D-RE"
    USABILIDAD_AUTOMATIZABLE = "D-US"


class EstadoNormalizado(StrEnum):
    FAVORABLE = "favorable"
    INTERMEDIO = "intermedio"
    DESFAVORABLE = "desfavorable"
    REQUIERE_REVISION = "requiere_revision"
    NO_EVALUADO = "no_evaluado"


class Prioridad(StrEnum):
    CRITICA = "critica"
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"
    REVISION = "revision"

