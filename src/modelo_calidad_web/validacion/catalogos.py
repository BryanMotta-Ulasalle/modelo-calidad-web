import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from modelo_calidad_web.dominio.resultado import ResultadoNormalizado


class ErrorCatalogo(ValueError):
    """Indica que un resultado no mantiene coherencia con los catálogos."""


def _cargar_json(ruta) -> list[dict[str, Any]]:
    with ruta.open("r", encoding="utf-8") as archivo:
        contenido = json.load(archivo)
    if not isinstance(contenido, list):
        raise ErrorCatalogo(f"El catálogo {ruta} debe contener una lista JSON")
    return contenido


@dataclass(frozen=True)
class Catalogos:
    dimensiones: dict[str, dict[str, Any]]
    indicadores: dict[str, dict[str, Any]]
    estados: dict[str, dict[str, Any]]
    prioridades: set[str]
    reglas_normalizacion: dict[str, dict[str, Any]]

    def validar_resultado(self, resultado: ResultadoNormalizado) -> None:
        indicador = self.indicadores.get(resultado.id_indicador)
        if indicador is None:
            raise ErrorCatalogo(
                f"El indicador {resultado.id_indicador} no existe en el catálogo"
            )

        dimension = resultado.id_dimension.value
        if dimension not in self.dimensiones:
            raise ErrorCatalogo(f"La dimensión {dimension} no existe en el catálogo")

        if indicador["dimension"] != dimension:
            raise ErrorCatalogo(
                f"El indicador {resultado.id_indicador} pertenece a "
                f"{indicador['dimension']} y no a {dimension}"
            )

        estado = resultado.estado_normalizado.value
        if estado not in self.estados:
            raise ErrorCatalogo(f"El estado {estado} no existe en el catálogo")

        if resultado.prioridad and resultado.prioridad.value not in self.prioridades:
            raise ErrorCatalogo(
                f"La prioridad {resultado.prioridad.value} no existe en el catálogo"
            )


def cargar_catalogos(directorio: str | Path | None = None) -> Catalogos:
    base = Path(directorio) if directorio else files("modelo_calidad_web").joinpath("catalogos")

    dimensiones_lista = _cargar_json(base.joinpath("dimensiones.json"))
    indicadores_lista = _cargar_json(base.joinpath("indicadores.json"))
    estados_lista = _cargar_json(base.joinpath("estados.json"))
    prioridades_lista = _cargar_json(base.joinpath("prioridades.json"))
    reglas_lista = _cargar_json(base.joinpath("reglas_normalizacion.json"))

    return Catalogos(
        dimensiones={item["id"]: item for item in dimensiones_lista},
        indicadores={item["id"]: item for item in indicadores_lista},
        estados={item["valor"]: item for item in estados_lista},
        prioridades={item["valor"] for item in prioridades_lista},
        reglas_normalizacion={item["id"]: item for item in reglas_lista},
    )

