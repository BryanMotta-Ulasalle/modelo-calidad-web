# Matriz de trazabilidad entre diseño y código

| Elemento de diseño | Implementación | Verificación inicial |
|---|---|---|
| CR-01 a CR-18 | `dominio/resultado.py` | `tests/test_resultado.py` |
| EI-02 Evaluación | `dominio/evaluacion.py` | Construcción validada por Pydantic |
| EI-03 Contexto de ejecución | `ContextoEjecucion` | Campos tipados y control de extras |
| D-AC, D-RE y D-US | `catalogos/dimensiones.json` | Conteo de tres dimensiones |
| A-01 a A-09 | `catalogos/indicadores.json` | Existencia y dimensión principal |
| P-01 a P-06 | `catalogos/indicadores.json` | Existencia y dimensión principal |
| U-01 a U-05 | `catalogos/indicadores.json` | Existencia y dimensión principal |
| EN-01 a EN-05 | `catalogos/estados.json` y enumeración | Enumeración cerrada y conteo |
| RN-01 | Campo `datosOriginales` | Presencia obligatoria en cada ejemplo |
| RN-02 | `versionHerramienta` y `fechaHora` | Campos obligatorios |
| RN-03 | `idIndicador` e `idDimension` | Coherencia comprobada por `Catalogos` |
| RN-04 a RN-10 | `reglas_normalizacion.json` | Catálogo cargado; lógica pendiente del Sprint 3 |
| WAVE | `wave_ejemplo.json` | Validación de estructura y catálogo |
| axe DevTools | `axe_ejemplo.json` | Validación de estructura y catálogo |
| Lighthouse | `lighthouse_ejemplo.json` | Validación de estructura, métrica y unidad |

## Observación

La presencia de `RN-04` a `RN-10` en el catálogo no significa que sus algoritmos ya estén implementados. En este sprint se establece su representación configurable; su aplicación automática corresponde al Sprint de implementación 3.

