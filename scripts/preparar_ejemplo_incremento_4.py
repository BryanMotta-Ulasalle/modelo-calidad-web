"""Prepara dos vistas SIMULADAS; no abre navegadores ni accede al Portal Académico.

Ejecutar desde la raíz:
python scripts/preparar_ejemplo_incremento_4.py --salida salidas/ejemplo_incremento4
La carpeta de salida debe ser nueva. Contiene lotes clasificados y el manifiesto.
"""

import argparse
import hashlib
import json
from pathlib import Path

from modelo_calidad_web.importacion import importar_archivo
from modelo_calidad_web.procesamiento import clasificar_lote

RAIZ = Path(__file__).resolve().parents[1]


def preparar(salida: str | Path, *, comparar: bool = False) -> Path:
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=False)
    vistas = []
    for nombre in ("inicio", "cursos"):
        fuentes, lotes = [], {}
        for etiqueta, formato in (("wave", "wave-extension-captura-v2"),
                                   ("axe", "axe-core-playwright"), ("lighthouse", "lighthouse-result")):
            archivo = RAIZ / f"datos/ejemplos/incremento_4/{nombre}_{etiqueta}.json"
            importado = importar_archivo(
                archivo, formato, f"EVAL-SIMULADA-{nombre}", f"VISTA-{nombre}",
                perfil="incremento-3", ejecutor="playwright" if etiqueta == "axe" else None)
            lote = clasificar_lote(importado)
            destino = salida / f"{nombre}_{etiqueta}_clasificado.json"
            texto = lote.model_dump_json(by_alias=True, indent=2) + "\n"
            destino.write_bytes(texto.encode("utf-8"))
            fuentes.append({"idFuente": f"{nombre}-{etiqueta}", "ruta": destino.name,
                            "sha256": hashlib.sha256(destino.read_bytes()).hexdigest()})
            lotes[etiqueta] = lote
        wave = next(r for r in lotes["wave"].resultados if r.origen.identificador_origen == "alt_missing")
        axe = next(r for r in lotes["axe"].resultados if r.origen.identificador_origen == "image-alt")
        vistas.append({
            "idModuloVista": f"VISTA-{nombre}", "nombre": f"Vista {nombre} SIMULADA",
            "url": f"https://simulado.invalid/{nombre}",
            "grupos": [{
                "idGrupo": f"GRUPO-{nombre}", "idEvaluacion": f"EVAL-SIMULADA-{nombre}",
                "inicio": "2026-11-04T10:00:00-05:00", "fin": "2026-11-04T10:05:00-05:00",
                "perfilAcceso": "simulado", "perfilRendimiento": "mobile",
                "condicionesDeclaradas": {"navegador": "SIMULADO", "red": "SIMULADA",
                                           "cpu": "SIMULADA", "ventanaAncho": 390, "ventanaAlto": 844},
                "justificacionComparabilidad": "Datos construidos para un mismo contexto SIMULADO; no son capturas.",
                "fuentes": fuentes,
                "coincidencias": [{
                    "idCoincidencia": f"C-{nombre}-logo",
                    "referencias": [
                        {"idFuente": f"{nombre}-wave", "idResultado": wave.origen.id_resultado},
                        {"idFuente": f"{nombre}-axe", "idResultado": axe.origen.id_resultado, "indiceNodo": 0},
                    ],
                    "elementoCanonico": "#logo", "problemaComun": "Alternativa textual ausente SIMULADA.",
                    "responsable": "REVISOR SIMULADO",
                    "fechaHora": "2026-11-04T10:06:00-05:00",
                    "fundamento": "Equivalencia construida en los datos de prueba; no inferida por el programa.",
                    "evidencia": "SIMULADA: WAVE #logo corresponde al primer nodo axe #logo; el segundo nodo es otro elemento.",
                }],
            }],
        })
    manifiesto = {
        "versionEsquema": "0.4.1", "idCaso": "CASO-SIMULADO-INC4",
        "titulo": "Demostración de integración con dos vistas simuladas",
        "tipoDatos": "simulados", "alcance": "Solo datos controlados; ninguna vista del Portal Académico.",
        "vistas": vistas,
        "comparaciones": [{
            "idComparacion": "COMPARACION-SIMULADA", "grupos": ["GRUPO-inicio", "GRUPO-cursos"],
            "protocolo": "SIMULADO: mismos datos de entorno y configuración; comparar métricas individuales.",
            "responsable": "INVESTIGADOR SIMULADO", "fechaHora": "2026-11-04T11:00:00-05:00",
            "condicionesComunes": vistas[0]["grupos"][0]["condicionesDeclaradas"],
            "maxDiferenciaSegundos": 3600,
        }] if comparar else [],
    }
    ruta = salida / "manifiesto.json"
    ruta.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ruta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--comparar", action="store_true", help="Añade un protocolo de comparación SIMULADO.")
    argumentos = parser.parse_args()
    print(preparar(argumentos.salida, comparar=argumentos.comparar))

