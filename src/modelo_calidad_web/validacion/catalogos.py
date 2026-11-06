from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from modelo_calidad_web.dominio.resultado import ResultadoNormalizado
from modelo_calidad_web.json_seguro import json_estricto


class ErrorCatalogo(ValueError):
    """Indica que un resultado no mantiene coherencia con los catálogos."""


def _cargar_json(ruta) -> list[dict[str, Any]]:
    try:
        contenido = json_estricto(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        raise ErrorCatalogo(f"No se puede leer {ruta}: {error}") from error
    if not isinstance(contenido, list) or not contenido:
        raise ErrorCatalogo(f"El catálogo {ruta} debe contener una lista no vacía")
    return contenido


def _indexar(filas, clave, campos, nombre):
    indice = {}
    for fila in filas:
        if not isinstance(fila, dict) or any(
                not isinstance(fila.get(c), str) or not fila[c].strip() for c in campos):
            raise ErrorCatalogo(f"Campos obligatorios inválidos en {nombre}")
        valor = fila[clave]
        if valor != valor.strip() or valor in indice:
            raise ErrorCatalogo(f"Identificador repetido o con espacios en {nombre}: {valor}")
        indice[valor] = fila
    return indice



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

    dimensiones = _indexar(dimensiones_lista, "id", ("id", "nombre", "proposito"), "dimensiones")
    indicadores = _indexar(indicadores_lista, "id", ("id", "nombre", "dimension"), "indicadores")
    estados = _indexar(estados_lista, "valor", ("id", "valor", "nombre"), "estados")
    _indexar(estados_lista, "id", ("id",), "estados")
    prioridades = _indexar(prioridades_lista, "valor", ("valor", "nombre"), "prioridades")
    reglas = _indexar(reglas_lista, "id", ("id", "nombre", "descripcion"), "reglas")
    for indicador in indicadores.values():
        if indicador["dimension"] not in dimensiones:
            raise ErrorCatalogo(f"Dimensión inexistente de {indicador['id']}")
        referencias = indicador.get("referencias")
        if referencias is not None and (not isinstance(referencias, list) or not referencias
                or any(not isinstance(r, str) or not r.strip() for r in referencias)):
            raise ErrorCatalogo(f"Referencias inválidas de {indicador['id']}")
    return Catalogos(dimensiones=dimensiones, indicadores=indicadores, estados=estados,
                     prioridades=set(prioridades), reglas_normalizacion=reglas)
