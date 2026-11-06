"""Lectura JSON común: sin claves repetidas ni valores no finitos."""

import json


def json_estricto(texto):
    def constante(valor):
        raise ValueError(f"constante JSON no admitida: {valor}")

    def pares(items):
        objeto = {}
        for clave, valor in items:
            if clave in objeto:
                raise ValueError(f"clave JSON repetida: {clave}")
            objeto[clave] = valor
        return objeto

    datos = json.loads(texto, parse_constant=constante, object_pairs_hook=pares)
    json.dumps(datos, allow_nan=False)
    return datos
