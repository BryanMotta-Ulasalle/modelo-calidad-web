import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .dominio.resultado import ResultadoNormalizado
from .json_seguro import json_estricto
from .importacion import ErrorImportacion, importar_archivo
from .integracion import diagnosticar_archivo, generar_informe
from .procesamiento import ErrorProcesamiento, clasificar_archivo, registrar_revision_archivo
from .validacion.catalogos import ErrorCatalogo, cargar_catalogos


def validar_archivo(ruta: Path, directorio_catalogos: str | None = None) -> None:
    datos = json_estricto(ruta.read_bytes().decode("utf-8"))

    resultado = ResultadoNormalizado.model_validate(datos)
    catalogos = cargar_catalogos(directorio_catalogos)
    catalogos.validar_resultado(resultado)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modelo-calidad-web",
        description="Valida, importa, clasifica e integra datos para el modelo de calidad web.",
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
    importar = subparsers.add_parser(
        "importar", help="Importa una captura o reporte a la etapa intermedia."
    )
    importar.add_argument("archivo", type=Path)
    importar.add_argument("--formato", required=True, choices=(
        "wave-extension-captura-v1", "wave-extension-captura-v2", "axe-core-playwright", "lighthouse-result"))
    importar.add_argument("--perfil", choices=("incremento-2", "incremento-3"), default="incremento-2",
                           help="Activa explícitamente los adaptadores ampliados del tercer incremento.")
    importar.add_argument("--id-evaluacion", required=True)
    importar.add_argument("--id-modulo-vista", required=True)
    importar.add_argument("--catalogo-mapeos", type=Path)
    importar.add_argument("--ejecutor", choices=("playwright",),
                           help="Declaración externa obligatoria para axe-core; no prueba su procedencia.")
    importar.add_argument("--manifiesto-procedimiento", type=Path,
                           help="Manifiesto de axe vinculado al JSON por hash, URL y versión.")
    importar.add_argument("--salida", type=Path, required=True,
                           help="Archivo JSON nuevo para el lote importado; no se sobrescribe.")
    clasificar = subparsers.add_parser(
        "clasificar", help="Aplica reglas del tercer incremento a un lote importado 0.2.0 o 0.3.0."
    )
    clasificar.add_argument("archivo", type=Path)
    clasificar.add_argument("--salida", type=Path, required=True,
                            help="Archivo nuevo para decisiones trazables; no se sobrescribe.")
    revisar = subparsers.add_parser(
        "revisar", help="Anexa una revisión humana documentada a un resultado pendiente."
    )
    revisar.add_argument("archivo", type=Path, help="Lote procesado.")
    revisar.add_argument("--registro", type=Path, required=True,
                         help="JSON con responsable, fecha, estado revisado, fundamento y evidencia.")
    revisar.add_argument("--salida", type=Path, required=True, help="Archivo nuevo con el historial ampliado.")
    diagnosticar = subparsers.add_parser(
        "diagnosticar", help="Integra lotes clasificados según un manifiesto explícito de vistas y contextos."
    )
    diagnosticar.add_argument("archivo", type=Path, help="Manifiesto JSON del caso.")
    diagnosticar.add_argument("--salida", type=Path, required=True, help="Diagnóstico JSON nuevo.")
    informe = subparsers.add_parser("informe", help="Verifica un diagnóstico y genera un informe Markdown.")
    informe.add_argument("archivo", type=Path, help="Diagnóstico JSON del cuarto incremento.")
    informe.add_argument("--salida", type=Path, required=True, help="Informe Markdown nuevo.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    errores = 0

    if args.comando == "validar":
        for ruta in args.archivos:
            try:
                validar_archivo(ruta, args.catalogos)
                print(f"[OK] {ruta}: resultado válido")
            except (OSError, ValueError, UnicodeError) as error:
                errores += 1
                print(f"[ERROR] {ruta}: {error}", file=sys.stderr)

    if args.comando == "importar":
        try:
            lote = importar_archivo(args.archivo, args.formato, args.id_evaluacion,
                                   args.id_modulo_vista, catalogo_mapeos=args.catalogo_mapeos,
                                   ejecutor=args.ejecutor,
                                   manifiesto_procedimiento=args.manifiesto_procedimiento, perfil=args.perfil)
            with args.salida.open("x", encoding="utf-8") as archivo:
                archivo.write(lote.model_dump_json(by_alias=True, indent=2))
                archivo.write("\n")
            print(f"[OK] {args.archivo}: {len(lote.resultados)} resultado(s) importado(s) a {args.salida}; estados pendientes")
        except ErrorImportacion as error:
            errores += 1
            print(f"[ERROR:{error.codigo}] {args.archivo}: {error}", file=sys.stderr)
        except OSError as error:
            errores += 1
            print(f"[ERROR:ARCHIVO] {args.archivo}: {error}", file=sys.stderr)

    if args.comando in {"diagnosticar", "informe"}:
        try:
            if args.comando == "diagnosticar":
                diagnostico = diagnosticar_archivo(args.archivo)
                texto = diagnostico.model_dump_json(by_alias=True, indent=2) + "\n"
            else:
                texto = generar_informe(args.archivo)
            with args.salida.open("x", encoding="utf-8") as archivo:
                archivo.write(texto)
            print(f"[OK] {args.comando}: {args.salida}")
        except ErrorProcesamiento as error:
            errores += 1
            print(f"[ERROR:{error.codigo}] {args.archivo}: {error}", file=sys.stderr)
        except OSError as error:
            errores += 1
            print(f"[ERROR:ARCHIVO] {args.archivo}: {error}", file=sys.stderr)

    if args.comando in {"clasificar", "revisar"}:
        try:
            lote = (clasificar_archivo(args.archivo) if args.comando == "clasificar" else
                    registrar_revision_archivo(args.archivo, args.registro))
            # Serializar antes de crear el archivo evita una salida vacía por fallo de formato.
            texto = lote.model_dump_json(by_alias=True, indent=2) + "\n"
            with args.salida.open("x", encoding="utf-8") as archivo:
                archivo.write(texto)
            if args.comando == "clasificar":
                pendientes = sum(r.decision.revision == "pendiente" for r in lote.resultados)
                print(f"[OK] {len(lote.resultados)} decisión(es); {pendientes} revisión(es) pendiente(s); {args.salida}")
            else:
                print(f"[OK] revisión registrada; {len(lote.historial_revisiones)} registro(s); {args.salida}")
        except ErrorProcesamiento as error:
            errores += 1
            print(f"[ERROR:{error.codigo}] {args.archivo}: {error}", file=sys.stderr)
        except OSError as error:
            errores += 1
            print(f"[ERROR:ARCHIVO] {args.archivo}: {error}", file=sys.stderr)

    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
