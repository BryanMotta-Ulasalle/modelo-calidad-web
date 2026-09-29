import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .dominio.resultado import ResultadoNormalizado
from .validacion.catalogos import ErrorCatalogo, cargar_catalogos


def validar_archivo(ruta: Path, directorio_catalogos: str | None = None) -> None:
    with ruta.open("r", encoding="utf-8") as archivo:
        datos = json.load(archivo)

    resultado = ResultadoNormalizado.model_validate(datos)
    catalogos = cargar_catalogos(directorio_catalogos)
    catalogos.validar_resultado(resultado)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modelo-calidad-web",
        description="Valida resultados normalizados del modelo de calidad web.",
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)
    validar = subparsers.add_parser(
        "validar", help="Valida uno o más archivos JSON normalizados."
    )
    validar.add_argument("archivos", nargs="+", type=Path)
    validar.add_argument(
        "--catalogos",
        help="Directorio alternativo que contiene los catálogos JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    errores = 0

    if args.comando == "validar":
        for ruta in args.archivos:
            try:
                validar_archivo(ruta, args.catalogos)
                print(f"[OK] {ruta}: resultado válido")
            except (OSError, json.JSONDecodeError, ValidationError, ErrorCatalogo) as error:
                errores += 1
                print(f"[ERROR] {ruta}: {error}", file=sys.stderr)

    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
