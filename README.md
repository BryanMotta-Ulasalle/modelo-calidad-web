# Modelo de evaluación automatizada de calidad web

Prototipo de apoyo que conserva el incremento 0.1.0 e incorpora la importación del incremento **0.2.0** de la tesis:

> Desarrollo de un modelo de evaluación automatizada de calidad web para el Portal Académico de la Universidad La Salle - Arequipa.

La base 0.1.0 implementa la estructura común `CR-01` a `CR-18` y valida ejemplos controlados. El incremento 0.2.0 incorpora lectores de una transcripción manual estructurada de WAVE, un JSON de `axe.run` y un Lighthouse Result JSON. Además de los ejemplos simulados, se incluyen muestras de una página pública para probar los importadores. No se han procesado reportes del Portal Académico.

## Requisitos

- Python 3.11 o posterior.
- Pydantic 2.x.

## Instalación en Windows

Abra PowerShell o la terminal de Visual Studio Code dentro de la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Si `python` no está disponible, utilice el nombre o la ruta de una instalación de Python 3.11 o posterior para crear el entorno.

## Validar los tres ejemplos

```powershell
.\.venv\Scripts\python.exe -m modelo_calidad_web validar datos/ejemplos/wave_ejemplo.json datos/ejemplos/axe_ejemplo.json datos/ejemplos/lighthouse_ejemplo.json
```

También puede utilizar el comando instalado `.\.venv\Scripts\modelo-calidad-web.exe`. Si se ejecuta desde el código fuente sin instalar el paquete, debe definirse `PYTHONPATH`:

```powershell
$env:PYTHONPATH="src"
python -m modelo_calidad_web validar datos/ejemplos/wave_ejemplo.json datos/ejemplos/axe_ejemplo.json datos/ejemplos/lighthouse_ejemplo.json
```

El resultado esperado para cada archivo es `[OK] ... resultado válido`.

## Ejecutar las pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Organización

- `src/modelo_calidad_web/dominio/`: modelos y enumeraciones del dominio.
- `src/modelo_calidad_web/catalogos/`: dimensiones, indicadores, estados, prioridades y reglas.
- `src/modelo_calidad_web/validacion/`: carga y comprobación cruzada de catálogos.
- `src/modelo_calidad_web/importacion/`: lectores y contrato de etapa intermedia.
- `datos/ejemplos/`: entradas controladas; no son resultados del caso de estudio.
- `datos/muestras_publicas/`: entradas, evidencia y salidas de una página pública de demostración.
- `scripts/`: captura reproducible de muestras públicas con WAVE, axe-core y Lighthouse.
- `tests/`: pruebas automáticas del incremento.

Los documentos de trabajo de la tesis se conservan localmente en `docs/` y no forman parte del repositorio.

## Importar a la etapa intermedia 0.2.0

Use `.venv\Scripts\python.exe` en PowerShell para no depender de la activación del entorno. La salida se guarda en un archivo **nuevo** y nunca reemplaza el archivo fuente:

```powershell
.\.venv\Scripts\python.exe -m modelo_calidad_web importar datos/ejemplos/wave_captura_controlada_v1.json --formato wave-extension-captura-v1 --id-evaluacion EVAL-PRUEBA-002 --id-modulo-vista MOD-INICIO --salida wave_importado.json
.\.venv\Scripts\python.exe -m modelo_calidad_web importar datos/ejemplos/axe_core_playwright_controlado.json --formato axe-core-playwright --ejecutor playwright --id-evaluacion EVAL-PRUEBA-002 --id-modulo-vista MOD-INICIO --salida axe_importado.json
.\.venv\Scripts\python.exe -m modelo_calidad_web importar datos/ejemplos/lighthouse_result_controlado.json --formato lighthouse-result --id-evaluacion EVAL-PRUEBA-002 --id-modulo-vista MOD-INICIO --salida lighthouse_importado.json
```

`--ejecutor playwright` es una **declaración externa**: un JSON de `axe.run` normalmente registra `testRunner` de axe, no prueba por sí solo que Playwright lo haya ejecutado. El lote guarda la declaración y el `testRunner` original por separado. Los códigos de error son `FORMATO`, `DATOS_INSUFICIENTES`, `SIN_MAPEO` y `ARCHIVO` para un fallo al crear la salida. El comando termina con código 0 al importar o 1 si falla. Puede pasar `--catalogo-mapeos` para un catálogo versionado alternativo; cada entrada debe mapear un identificador fuente con indicador, dimensión y referencias coherentes.

Para axe se puede añadir `--manifiesto-procedimiento ruta.json`. La CLI compara el SHA-256, la URL final y `testEngine` del manifiesto con el archivo original y registra esa evidencia aparte de `ejecutorDeclarado`. El manifiesto por sí solo no certifica quién lo creó.

El archivo resultante conserva el texto original exacto en `textoOriginal`, su SHA-256 en `sha256Original`, el objeto completo en `entradaOriginal` y el fragmento fuente de cada resultado en `datosOriginales`. `contexto`, `versionHerramienta` y `versionCatalogoMapeos` registran la procedencia disponible. Cada `ResultadoImportado` tiene `estadoNormalizado: null` y `prioridad: null`. No pase ese lote a `validar`: ese comando sigue aceptando un **único `ResultadoNormalizado` ya clasificado**.

La entrada WAVE es una captura estructurada documentada y transcrita manualmente, **no** una exportación JSON nativa de la extensión. Para axe-core se espera el JSON completo de `axe.run`; para Lighthouse, el Lighthouse Result JSON. El catálogo de mapeos cubre los identificadores declarados en él: uno desconocido produce `SIN_MAPEO`. Los ejemplos de `datos/ejemplos/` son construcciones controladas, no exportaciones auténticas de esas herramientas. La importación termina en una etapa intermedia; todavía no calcula estados, prioridades ni un diagnóstico.

## Muestras de una página pública

`datos/muestras_publicas/` contiene capturas de la [página de demostración W3C](https://www.w3.org/WAI/demos/bad/before/home.html): salida de la extensión WAVE y dos hallazgos transcritos manualmente, JSON completo de axe-core ejecutado por Playwright y Lighthouse Result JSON. También contiene los manifiestos de procedimiento y las salidas importadas. En esa muestra se importaron dos hallazgos WAVE, ocho resultados de axe-core y cinco métricas de Lighthouse. Los demás datos permanecen en los archivos originales. Son muestras de una página pública, **no del Portal Académico**. Las pruebas estáticas de regresión pueden ejecutarse sin Internet, Chrome ni Node; repetir las capturas sí requiere las herramientas externas y puede producir resultados distintos.

Para repetir la captura, instale Node.js, prepare los paquetes locales y configure una **carpeta de salida nueva** para conservar las muestras incluidas:

```powershell
npm install --prefix .tools --no-save playwright-core@1.63.0 axe-core@4.14.0 lighthouse@13.5.0
$env:PLAYWRIGHT_BROWSERS_PATH = (Join-Path (Get-Location).Path '.tools\browsers')
node .tools\node_modules\playwright-core\cli.js install chromium
$env:WAVE_EXTENSION_DIR = '<carpeta-de-la-extension-WAVE-instalada>'
$env:CHROME_PATH = '<ruta-de-chrome.exe>'
$env:SALIDA_MUESTRAS = (Join-Path (Get-Location).Path '.tools\repeticion')
node scripts\capturar_wave_publico.cjs
node scripts\capturar_axe_publico.cjs
node scripts\capturar_lighthouse_publico.cjs
```

La transcripción WAVE incluida se hizo manualmente a partir de la captura y solo representa dos de los iconos observados. El archivo interno completo de WAVE y la captura de pantalla sirven como evidencia de esa transcripción, pero la CLI no los importa directamente. Los manifiestos registran versiones, URL y SHA-256; vinculan los archivos compartidos, sin demostrar por sí solos la autoría de una ejecución.

## Alcance actual

La base del incremento 0.1.0 incluye:

- Validación estructural de los campos `CR-01` a `CR-18`.
- Conservación de `datosOriginales` para cumplir `RN-01`.
- Tres dimensiones, veinte indicadores, cinco estados y diez reglas de normalización.
- Validación de coherencia entre indicador y dimensión.
- Ejemplos controlados de las tres herramientas.

El incremento 0.2.0 añade la importación a la etapa intermedia descrita arriba y las pruebas con muestras de una página pública. Todavía no incluye:

- Aplicación automática de reglas y umbrales.
- Integración por dimensión o módulo.
- Generación del diagnóstico final.
- Ejecuciones sobre el Portal Académico.

Esas capacidades corresponden a los siguientes incrementos. El prototipo no hace una evaluación completa de usabilidad, no certifica conformidad WCAG y no produce un puntaje global único.
