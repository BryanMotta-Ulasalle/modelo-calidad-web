"""Integración estructural del modelo: sin agregación numérica global."""

from .motor import diagnosticar_archivo, verificar_diagnostico_archivo
from .informe import generar_informe

__all__ = ["diagnosticar_archivo", "verificar_diagnostico_archivo", "generar_informe"]

