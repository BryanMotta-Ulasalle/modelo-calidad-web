# Arquitectura técnica del Sprint 1

## Objetivo

Construir la base ejecutable del prototipo sin adelantar la integración de herramientas ni la demostración sobre el caso de estudio.

## Capas implementadas

1. **Entrada controlada:** archivos JSON que representan resultados ya mapeados.
2. **Dominio:** modelos `ResultadoNormalizado`, `Evaluacion` y `ContextoEjecucion`.
3. **Catálogos:** dimensiones, indicadores, estados, prioridades y reglas de normalización.
4. **Validación:** comprobaciones estructurales y coherencia indicador–dimensión.
5. **Interfaz inicial:** comando de consola para validar uno o varios resultados.

## Decisiones

- El núcleo se implementa en Python por su adecuación al procesamiento estructurado y al análisis posterior.
- JSON se usa como formato de intercambio porque las herramientas producen estructuras diferentes y se requiere conservar el dato fuente.
- Pydantic valida tipos, campos obligatorios y enumeraciones.
- Los catálogos permanecen fuera de la lógica para permitir ajustes versionados.
- No se utiliza una base de datos en este incremento porque todavía no existe una necesidad de persistencia demostrada.
- No se implementa una interfaz gráfica: el objetivo es validar el núcleo del artefacto.

## Flujo actual

1. El usuario proporciona un JSON normalizado.
2. El modelo valida los campos `CR-01` a `CR-18`.
3. Se comprueba que indicador, dimensión, estado y prioridad existan en los catálogos.
4. Se verifica que el indicador pertenezca a la dimensión declarada.
5. El comando informa si el resultado es válido o muestra el error detectado.

## Límite del incremento

Los archivos de `datos/ejemplos` son datos simulados y controlados. No representan una evaluación del Portal Académico y no deben utilizarse como resultados de la demostración.

