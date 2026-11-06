# Modelo de evaluación automatizada de calidad web

Prototipo de apoyo **0.3.0**. Conserva la validación y la importación anteriores e implementa la clasificación del tercer incremento de la tesis:

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
- `src/modelo_calidad_web/procesamiento/`: clasificación por reglas y registro de revisiones humanas.
- `datos/ejemplos/`: entradas controladas; no son resultados del caso de estudio.
- `datos/muestras_publicas/`: entradas, evidencia y salidas de una página pública de demostración.
- `datos/muestras_publicas_incremento3_verificadas/`: muestras y manifiestos usados para comprobar el tercer incremento.
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

El incremento 0.2.0 añade la importación a la etapa intermedia descrita arriba y las pruebas con muestras de una página pública. El tercer incremento añade clasificación para la cobertura delimitada a continuación. Todavía no incluye:

- Integración por dimensión o módulo.
- Generación del diagnóstico final.
- Ejecuciones sobre el Portal Académico.

Esas capacidades corresponden a los siguientes incrementos. El prototipo no hace una evaluación completa de usabilidad, no certifica conformidad WCAG y no produce un puntaje global único.

## Tercer incremento 0.3.0: clasificación y revisión documentada

Implementado y comprobado localmente. La versión del paquete, el motor y el esquema procesado son `0.3.0`; las reglas operativas son `1.0.0`. Esto no representa publicación remota, evaluación DSR concluida ni resultados del Portal Académico. El modelo es el aporte principal: el prototipo aplica sus decisiones y conserva la evidencia.

### Importación compatible y perfil ampliado

El comando `importar` conserva por defecto el perfil `incremento-2`, con esquema 0.2.0 y mapeos 1.1.0. Para activar las fuentes ampliadas use `--perfil incremento-3`: produce esquema 0.3.0 con mapeos 2.0.0. En ambos casos termina sin estados ni prioridades calculados; `clasificar` recibe el lote y aplica las reglas.

```powershell
New-Item -ItemType Directory -Force salidas
.\.venv\Scripts\python.exe -m modelo_calidad_web importar datos/ejemplos/wave_captura_controlada_v2.json --perfil incremento-3 --formato wave-extension-captura-v2 --id-evaluacion EVAL-SIMULADA --id-modulo-vista VISTA-SIMULADA --salida salidas/wave_importado_03.json
.\.venv\Scripts\python.exe -m modelo_calidad_web clasificar salidas/wave_importado_03.json --salida salidas/wave_clasificado_03.json
.\.venv\Scripts\python.exe -m modelo_calidad_web importar datos/muestras_publicas_incremento3_verificadas/lighthouse_12_raw.json --perfil incremento-3 --formato lighthouse-result --id-evaluacion EVAL-PUBLICA --id-modulo-vista EXAMPLE-PUBLICA --salida salidas/lighthouse_importado_03.json
.\.venv\Scripts\python.exe -m modelo_calidad_web clasificar salidas/lighthouse_importado_03.json --salida salidas/lighthouse_clasificado_03.json
```

Cada salida requiere un nombre nuevo: nunca se sobrescriben archivos. `salidas/`, `docs/`, `.tools/`, el entorno virtual y los productos de empaquetado quedan fuera de Git. Las entradas y expectativas de prueba de `datos/` sí forman parte del repositorio.

`validar` sigue aceptando un único resultado de la estructura anterior, no un lote importado o procesado. Para axe se mantiene `--ejecutor playwright` y el manifiesto opcional. El perfil nuevo identifica la herramienta como `axe-core`; los lotes anteriores conservan la etiqueta histórica `axe DevTools`, sin afirmar uso de esa extensión.

### Reglas y cobertura de esta versión

El catálogo ampliado relaciona 19 indicadores con fuentes concretas; P-06 se trata como contexto. Tener un mapeo no demuestra cobertura completa de un indicador ni que se haya evaluado en una ejecución.

- WAVE v2 admite categorías explícitas y coherentes con cada ID: `alt_missing` y `contrast` como hallazgos desfavorables; `alt_suspicious` como alerta que requiere revisión; `alt`, `h1` y `aria` como evidencia contextual sin estado ni prioridad. La captura es documentada, no una exportación JSON nativa. Se distingue transcripción manual de captura documentada asistida.
- La prioridad **alta** para `alt_missing` y `contrast` es una decisión operativa versionada del modelo, justificada por barreras de acceso detectadas. No es una severidad oficial de WAVE, una estimación de riesgo institucional ni una asignación general a cualquier error. Las alertas reciben prioridad de revisión; el contexto no se prioriza.
- Axe admite los cuatro grupos `violations/incomplete/passes/inapplicable` y selectores anidados. Se añaden `document-title` (A-05), `aria-valid-attr` y `aria-valid-attr-value` (A-08), `frame-focusable-content` (A-09) y `target-size` (U-03). A-09 cubre esa comprobación de marcos con contenido enfocable, no toda la operabilidad mediante teclado. U-02 y U-03 conservan D-US, sin duplicarlos en accesibilidad.
- Las infracciones axe son desfavorables; `critical/serious/moderate/minor` corresponden a prioridad `critica/alta/media/baja`. Una infracción sin impacto reconocido sigue desfavorable y sin prioridad. `incomplete` requiere revisión aunque su impacto sea serious. Un `pass` es favorable solo para la regla y los elementos comprobados; un `inapplicable` queda no evaluado.
- Lighthouse compara FCP/LCP/TBT/CLS/Speed Index sin redondeo previo. Los tiempos admitidos en segundos o milisegundos se normalizan a ms en el perfil ampliado. FCP/LCP/TBT/SI usan perfil móvil explícito; los demás perfiles quedan no evaluados con motivo. CLS tiene umbrales independientes del perfil. P-06 conserva la puntuación compuesta solo como contexto.
- Las auditorías técnicas `viewport` (U-01), `paste-preventing-inputs` (U-04) y `errors-in-console` (U-05) tienen contratos de versión y modo de resultado. Se comprueban pasa/falla/no aplicable/error. Los errores de consola requieren revisión del impacto. No se interpreta cualquier score numérico como un booleano.
- `viewport` se admite en Lighthouse **12.8.2**, cuya salida se comprobó. Lighthouse **13.5.0** admite aquí pegado y errores de consola. Su nuevo `viewport-insight` no se equipara al antiguo: una captura de esa versión sin `viewport` deja U-01 sin resultado y lo explica en la cobertura. La diferencia está documentada por [Chrome](https://developer.chrome.com/docs/lighthouse/best-practices/viewport).

El procesador conserva originales, valores normalizados, regla y versión, condiciones, motivos y hashes de fuente, archivo intermedio, reglas y mapeos. `coberturaIndicadores` registra los 20 indicadores con su situación en ese formato, sin inventar hallazgos para los ausentes. Los IDs no mapeados de passes/inapplicable se registran en un inventario separado, sin clasificarlos; los candidatos desconocidos de violations/incomplete continúan produciendo `SIN_MAPEO`.

El catálogo descriptivo de diez reglas RN se conserva. RN-07, la consolidación entre herramientas, integración, recomendaciones y diagnóstico final corresponden al siguiente incremento. El resultado de clasificación no es un puntaje global.

### Revisión humana

Una revisión pendiente no se marca realizada automáticamente. Una persona debe aportar un JSON con `idResultado`, `responsable`, `fechaHora` con zona horaria, `estadoRevisado`, `fundamento` y `evidencia`:

```powershell
.\.venv\Scripts\python.exe -m modelo_calidad_web revisar salidas/axe_clasificado_03.json --registro revision_documentada.json --salida salidas/axe_con_revision_03.json
```

Se anexa un registro con situación realizada, número, copia de la decisión automática y SHA-256 del lote previo. El último registro del historial de cada resultado contiene la decisión humana vigente; puede concluir que persiste la incertidumbre. `decision.revision` conserva la necesidad detectada originalmente. El mecanismo no autentica al revisor ni aporta firma digital. Las revisiones de las pruebas son simuladas y no se presentan como revisiones reales de las páginas.

### Evidencia y reproducción

`datos/muestras_publicas_incremento3_verificadas/` conserva nuevas ejecuciones sobre `https://example.com/`: axe-core 4.14.0 mediante Playwright 1.63.0 y Lighthouse 12.8.2/13.5.0, con manifiestos y auditoría HTTP satisfactoria en ambas capturas Lighthouse. WAVE v2 reestructura evidencia W3C del 6 de octubre: es una captura documentada asistida, no una nueva ejecución de la extensión. La categoría ARIA solo se ejercita en el ejemplo simulado.

Las muestras originales de `datos/muestras_publicas/` permanecen intactas. Un intento adicional sobre W3C con errores 403 y sin verificación HTTP suficiente se conserva localmente y está excluido de Git; no se utiliza como demostración de la vista esperada.

Las pruebas estáticas no necesitan navegador, Node ni Internet. Para repetir las capturas, prepare las herramientas locales y utilice una carpeta de salida nueva:

```powershell
npm install --prefix .tools --no-save --ignore-scripts playwright-core@1.63.0 axe-core@4.14.0 lighthouse@13.5.0 lighthouse-legacy@npm:lighthouse@12.8.2
$env:CHROME_PATH = '<ruta-de-Chrome-instalado>'
$env:URL_MUESTRA = 'https://example.com/'
$env:SALIDA_MUESTRAS = 'salidas/captura_nueva'
node scripts/capturar_incremento_3.cjs
```

La captura se limita a las dos páginas públicas declaradas en el script y conserva fuentes y manifiestos. Los hashes comprueban contenido y coherencia; por sí solos no acreditan autoría o ejecución auténtica. Una nueva captura puede cambiar los valores y hallazgos.

Las pruebas incluyen fronteras numéricas, conversiones completas, categorías WAVE, estados axe, auditorías técnicas, versiones, ausencia de datos, integridad, revisión simulada y archivos sin sobrescritura. Las expectativas fueron preparadas durante el desarrollo; no equivalen a validación independiente por expertos. La evaluación DSR del modelo y su aplicación institucional requieren su procedimiento y evidencia propios.
