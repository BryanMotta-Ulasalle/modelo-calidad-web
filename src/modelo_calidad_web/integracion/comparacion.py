"""Comparabilidad y prioridad: decisiones explícitas del modelo, sin nota global."""

import json
from collections import defaultdict

from modelo_calidad_web.procesamiento.motor import ErrorProcesamiento


def canonico(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def comparar(manifiesto, vistas, fuentes):
    declarados = {g.id_grupo: (v, g) for v in manifiesto.vistas for g in v.grupos}
    integrados = {g.id_grupo: g for v in vistas for g in v.grupos}
    por_fuente = {f.id_fuente: f for f in fuentes}
    salida = []
    for comparacion in manifiesto.comparaciones:
        if any(id_ not in declarados for id_ in comparacion.grupos):
            raise ErrorProcesamiento("COMPARACION_INVALIDA", "grupo inexistente en comparación")
        pares = [declarados[id_] for id_ in comparacion.grupos]
        if len({v.id_modulo_vista for v, _ in pares}) != len(pares):
            raise ErrorProcesamiento("COMPARACION_INVALIDA", "comparar requiere vistas diferentes")
        perfil = {(g.perfil_acceso, g.perfil_rendimiento) for _, g in pares}
        if len(perfil) != 1 or pares[0][1].perfil_rendimiento is None:
            raise ErrorProcesamiento("COMPARACION_INVALIDA", "perfiles diferentes o insuficientes")
        for _, g in pares:
            if any(canonico(g.condiciones_declaradas.get(k)) != canonico(valor)
                   for k, valor in comparacion.condiciones_comunes.items()):
                raise ErrorProcesamiento("COMPARACION_INVALIDA", "condiciones comunes no coinciden")
        todas = [por_fuente[f.id_fuente] for _, g in pares for f in g.fuentes]
        fechas = [f.lote.entrada_importada.fecha_hora for f in todas]
        if (max(fechas) - min(fechas)).total_seconds() > comparacion.max_diferencia_segundos:
            raise ErrorProcesamiento("COMPARACION_INVALIDA", "capturas fuera del intervalo del protocolo")
        if comparacion.fecha_hora < max(fechas):
            raise ErrorProcesamiento("COMPARACION_INVALIDA", "declaración anterior a las capturas")
        versiones = defaultdict(set)
        for f in todas:
            l = f.lote
            versiones[l.motor_fuente].add((l.entrada_importada.version_herramienta,
                                          l.version_reglas, l.sha256_reglas, l.sha256_catalogo_mapeos))
        if any(len(v) != 1 for v in versiones.values()):
            raise ErrorProcesamiento("COMPARACION_INVALIDA", "versiones de herramientas/reglas incompatibles")
        metricas = []
        for id_indicador in ("P-01", "P-02", "P-03", "P-04", "P-05"):
            filas, firmas = [], []
            motivo = None
            for v, g in pares:
                i = next(i for d in integrados[g.id_grupo].dimensiones for i in d.indicadores
                         if i.id_indicador == id_indicador)
                fila = {"idModuloVista": v.id_modulo_vista, "idGrupo": g.id_grupo,
                        "mediciones": i.metricas}
                filas.append(fila)
                if len(i.metricas) != 1:
                    motivo = "sin_medicion_unica_por_grupo"
                    continue
                m = i.metricas[0]
                if m["estado"] not in {"favorable", "intermedio", "desfavorable"}:
                    motivo = "metrica_no_evaluada"
                l = por_fuente[m["idFuente"]].lote
                ctx = l.entrada_importada.contexto
                firmas.append(canonico({
                    "version": l.entrada_importada.version_herramienta, "reglas": l.sha256_reglas,
                    "config": ctx.get("configSettings"), "environment": ctx.get("environment"),
                    "userAgent": ctx.get("userAgent"), "unidad": m["unidadNormalizada"],
                }))
            if len(set(firmas)) > 1:
                motivo = "configuracion_observada_incompatible"
            if motivo is None:
                base = filas[0]["mediciones"][0]["valorNormalizado"]
                for fila in filas:
                    fila["diferenciaRespectoPrimerGrupo"] = fila["mediciones"][0]["valorNormalizado"] - base
            metricas.append({"idIndicador": id_indicador,
                             "situacion": "no_comparable" if motivo else "comparable",
                             "motivo": motivo, "filas": filas})
        salida.append({
            "idComparacion": comparacion.id_comparacion, "grupos": comparacion.grupos,
            "protocolo": comparacion.protocolo, "responsableDeclarado": comparacion.responsable,
            "condicionesComunes": comparacion.condiciones_comunes,
            "maxDiferenciaSegundos": comparacion.max_diferencia_segundos,
            "metricas": metricas,
            "coberturaPorGrupo": [{"idGrupo": g.id_grupo, "dimensiones": {
                d.id_dimension: {"estadosObservados": d.estados_observados,
                                 "indicadoresSinObservaciones": [i.id_indicador for i in d.indicadores
                                                                 if i.situacion == "sin_observaciones"]}
                for d in integrados[g.id_grupo].dimensiones}} for _, g in pares],
            "limite": "Comparación descriptiva bajo protocolo declarado; sin ranking, "
                      "causalidad ni verificación de condiciones físicas no conservadas.",
        })
    return salida


def priorizar(recomendaciones, vistas, fuentes, comparaciones):
    por_fuente = {f.id_fuente: f for f in fuentes}
    grupos = {g.id_grupo: g for v in vistas for g in v.grupos}
    obs = {o.id_observacion: o for g in grupos.values() for o in g.observaciones}

    def regla(o):
        f = por_fuente[o.referencia.id_fuente]
        r = next(r for r in f.lote.resultados if r.origen.id_resultado == o.referencia.id_resultado)
        return (f.lote.motor_fuente, f.lote.entrada_importada.version_herramienta,
                r.origen.identificador_origen, f.lote.sha256_reglas)

    for r in recomendaciones:
        grupo = grupos[r.id_grupo]
        # Elementos de la misma acción/indicador y estado en ese grupo; las métricas
        # no identifican elementos de interfaz.
        miembros = [o for o in grupo.observaciones if o.id_indicador == r.id_indicador
                    and o.estado_vigente == obs[r.ids_observaciones[0]].estado_vigente
                    and o.id_dimension != "D-RE" and o.ubicacion]
        claves = {o.id_observacion: (o.referencia.id_fuente, canonico(o.ubicacion)) for o in miembros}
        padre = {clave: clave for clave in claves.values()}

        def raiz(c):
            while padre[c] != c:
                c = padre[c]
            return c

        for h in grupo.hallazgos:
            if h.id_coincidencia:
                cs = [claves[i] for i in h.ids_observaciones if i in claves]
                for c in cs[1:]:
                    padre[raiz(c)] = raiz(cs[0])
        por_archivo = defaultdict(set)
        for c in claves.values():
            por_archivo[c[0]].add(c)
        r.elementos_afectados_minimos = max((len({raiz(c) for c in cs}) for cs in por_archivo.values()), default=0)
        r.elementos_observados_maximos = len({raiz(c) for c in claves.values()})
        r.casos_revision_asociados = sum(o.id_indicador == r.id_indicador and o.pendiente_revision
                                         for o in grupo.observaciones)
        reglas = {regla(obs[i]) for i in r.ids_observaciones}
        vistas_con_regla = {r.id_modulo_vista}
        for c in comparaciones:
            if r.id_grupo not in c["grupos"]:
                continue
            # Cada protocolo se evalúa por separado: no inferir transitividad entre
            # comparaciones A/B y B/C para fabricar una comparación A/C.
            candidatas = {r.id_modulo_vista}
            for v in vistas:
                for g in v.grupos:
                    if g.id_grupo in c["grupos"] and any(
                        o.id_indicador == r.id_indicador and
                        o.estado_vigente == obs[r.ids_observaciones[0]].estado_vigente and regla(o) in reglas
                        for o in g.observaciones):
                        if r.id_indicador.startswith("P-"):
                            m = next(m for m in c["metricas"] if m["idIndicador"] == r.id_indicador)
                            if m["situacion"] != "comparable":
                                continue
                        candidatas.add(v.id_modulo_vista)
            if len(candidatas) > len(vistas_con_regla):
                vistas_con_regla = candidatas
        r.vistas_con_misma_comprobacion = len(vistas_con_regla)
        r.criterio_desempate = (
            "Tras severidad: más vistas con misma comprobación/estado en un protocolo compatible, "
            "más elementos mínimos identificados del indicador/estado en el grupo y más revisiones "
            "asociadas. Límite superior no suma evidencia como elementos confirmados. "
            "Repetición de comprobación no demuestra identidad de causa entre vistas."
        )
    recomendaciones.sort(key=lambda r: (
        r.orden_tecnico, -r.vistas_con_misma_comprobacion, -r.elementos_afectados_minimos,
        -r.casos_revision_asociados, r.id_modulo_vista, r.id_grupo, r.id_recomendacion))

