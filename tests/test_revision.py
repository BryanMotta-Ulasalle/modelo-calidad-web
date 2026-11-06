"""Revisiones simuladas para comprobar registro, historial y conservación."""

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from modelo_calidad_web.main import main
from modelo_calidad_web.procesamiento import ErrorProcesamiento, clasificar_archivo, registrar_revision_archivo


class RevisionTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.base = Path(self.temporal.name)
        self.lote = clasificar_archivo(RAIZ / "datos/muestras_publicas/axe_importado.json")
        self.resultado = next(r for r in self.lote.resultados if r.decision.revision == "pendiente")
        self.ruta = self.base / "procesado.json"
        self.ruta.write_text(self.lote.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        self.registro = {
            "idResultado": self.resultado.origen.id_resultado,
            "responsable": "REVISOR SIMULADO PARA PRUEBA",
            "fechaHora": "2026-10-29T12:00:00-05:00",
            "estadoRevisado": "desfavorable",
            "fundamento": "DECISION SIMULADA: solo verifica el mecanismo de registro.",
            "evidencia": "EVIDENCIA SIMULADA: no corresponde a una revisión real del sitio.",
        }

    def guardar_registro(self, datos=None):
        ruta = self.base / "registro.json"
        ruta.write_text(json.dumps(self.registro if datos is None else datos), encoding="utf-8")
        return ruta

    def test_revision_conserva_decision_automatica_y_enlaza_archivo_previo(self):
        antes = self.ruta.read_bytes()
        salida = registrar_revision_archivo(self.ruta, self.guardar_registro())
        self.assertEqual(len(salida.historial_revisiones), 1)
        revision = salida.historial_revisiones[0]
        self.assertEqual(revision.sha256_lote_previo, hashlib.sha256(antes).hexdigest())
        self.assertEqual(revision.registro.estado_revisado, "desfavorable")
        self.assertEqual(revision.decision_automatica.estado_normalizado, "requiere_revision")
        self.assertEqual(salida.resultados, self.lote.resultados)
        self.assertEqual(self.ruta.read_bytes(), antes)

    def test_revision_exige_responsable_fecha_con_zona_fundamento_y_evidencia(self):
        for campo in ("responsable", "fechaHora", "fundamento", "evidencia"):
            with self.subTest(campo=campo):
                datos = copy.deepcopy(self.registro)
                del datos[campo]
                with self.assertRaises(ErrorProcesamiento):
                    registrar_revision_archivo(self.ruta, self.guardar_registro(datos))
        datos = {**self.registro, "fechaHora": "2026-10-29T12:00:00"}
        with self.assertRaises(ErrorProcesamiento):
            registrar_revision_archivo(self.ruta, self.guardar_registro(datos))

    def test_revision_rechaza_resultado_inexistente_o_sin_revision_pendiente(self):
        for id_resultado in ("inexistente", self.lote.resultados[0].origen.id_resultado):
            with self.subTest(id_resultado=id_resultado), self.assertRaises(ErrorProcesamiento):
                registrar_revision_archivo(self.ruta, self.guardar_registro({**self.registro, "idResultado": id_resultado}))

    def test_revision_detecta_decision_automatica_alterada(self):
        datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        datos["resultados"][0]["decision"]["estadoNormalizado"] = "favorable"
        self.ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(ErrorProcesamiento) as error:
            registrar_revision_archivo(self.ruta, self.guardar_registro())
        self.assertEqual(error.exception.codigo, "INTEGRIDAD")

    def test_segunda_revision_anexa_historial_y_rechaza_fecha_anterior(self):
        primera = registrar_revision_archivo(self.ruta, self.guardar_registro())
        segunda_ruta = self.base / "revision1.json"
        segunda_ruta.write_text(primera.model_dump_json(by_alias=True), encoding="utf-8")
        datos = {**self.registro, "fechaHora": "2026-10-29T12:30:00-05:00", "estadoRevisado": "requiere_revision"}
        segunda = registrar_revision_archivo(segunda_ruta, self.guardar_registro(datos))
        self.assertEqual([r.numero for r in segunda.historial_revisiones], [1, 2])
        self.assertEqual(segunda.historial_revisiones[0], primera.historial_revisiones[0])
        self.assertEqual(segunda.historial_revisiones[1].sha256_lote_previo,
                         hashlib.sha256(segunda_ruta.read_bytes()).hexdigest())
        datos["fechaHora"] = "2026-10-28T12:00:00-05:00"
        with self.assertRaises(ErrorProcesamiento):
            registrar_revision_archivo(segunda_ruta, self.guardar_registro(datos))

    def test_cli_revisar_no_sobrescribe_y_no_finge_revision_sin_registro(self):
        registro = self.guardar_registro()
        salida = self.base / "revisado.json"
        args = ["revisar", str(self.ruta), "--registro", str(registro), "--salida", str(salida)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 0)
        antes = salida.read_bytes()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 1)
        self.assertEqual(salida.read_bytes(), antes)
        self.assertEqual(self.lote.historial_revisiones, [])


if __name__ == "__main__":
    unittest.main()
