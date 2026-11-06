# Modelo de evaluación automatizada de calidad web

Prototipo de apoyo **0.4.1**. Conserva los contratos anteriores y añade integración por vista y dimensión, coincidencias documentadas, recomendaciones e informe del cuarto incremento de la tesis:

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

El incremento 0.2.0 añade la importación intermedia y las pruebas con muestras públicas. El tercero añade clasificación para la cobertura delimitada más abajo. El cuarto integra lotes mediante un manifiesto explícito y produce diagnóstico JSON e informe Markdown. La aplicación sobre el Portal Académico y la evaluación DSR del modelo siguen pendientes. El prototipo no hace una evaluación completa de usabilidad, no certifica conformidad WCAG y no produce un puntaje global único.

## Tercer incremento 0.3.0: clasificación y revisión documentada

Implementado y comprobado localmente en el cierre 0.3.0. El motor y el esquema clasificado se conservan en `0.3.0` dentro del paquete actual; las reglas operativas de clasificación son `1.0.0`. Esto no representa publicación remota, evaluación DSR concluida ni resultados del Portal Académico. El modelo es el aporte principal: el prototipo aplica sus decisiones y conserva la evidencia.

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

El catálogo descriptivo de diez reglas RN se conserva. RN-07, la integración, las recomendaciones y el diagnóstico se implementan en la etapa separada del cuarto incremento, descrita al final. El resultado de `clasificar` sigue sin consolidar y no es un puntaje global.

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

## Cuarto incremento 0.4.0: integración y diagnóstico

El modelo integra de forma estructural: caso → vista → grupo de observación → dimensión → indicador → observación. No combina dimensiones en una nota. El paquete/integrador y el diagnóstico actuales usan 0.4.1; el clasificador y sus lotes mantienen 0.3.0; las reglas de integración son 1.1.0 y las de clasificación 1.0.0, con versiones independientes.

### Recorrido con datos simulados

Desde la raíz, en una carpeta de salida **nueva**:

~~~powershell
.\.venv\Scripts\python.exe -B scripts/preparar_ejemplo_incremento_4.py --salida salidas/ejemplo_incremento4
.\.venv\Scripts\python.exe -B -m modelo_calidad_web diagnosticar salidas/ejemplo_incremento4/manifiesto.json --salida salidas/ejemplo_incremento4/diagnostico.json
.\.venv\Scripts\python.exe -B -m modelo_calidad_web informe salidas/ejemplo_incremento4/diagnostico.json --salida salidas/ejemplo_incremento4/informe.md
~~~

El primer comando **no captura páginas**: utiliza seis archivos controlados de datos/ejemplos/incremento_4/ para preparar dos vistas simuladas, sus lotes clasificados y un manifiesto con hashes. No contiene datos del Portal Académico. esperado.json conserva referencias fijadas para esta demostración; no se genera leyendo el diagnóstico ni constituye validación independiente.

En cada vista hay 17 resultados fuente y 18 observaciones, porque una regla axe contiene dos nodos. Una coincidencia simulada documentada reúne dos observaciones desfavorables del mismo problema y elemento; el otro nodo permanece independiente. Quedan nueve hallazgos/casos de atención y nueve recomendaciones por vista. Los conteos incluyen incertidumbre y mejora de métricas, no solo infracciones confirmadas.

### Manifiesto y compatibilidad de contexto

El manifiesto identifica idCaso, titulo, tipoDatos (simulados/publicos/institucionales), alcance y vistas. Cada vista declara idModuloVista, nombre, URL exacta y grupos.

Cada grupo declara idGrupo, idEvaluacion, inicio/fin con zona horaria, perfilAcceso, perfilRendimiento (mobile/desktop/null), condicionesDeclaradas, justificacionComparabilidad, fuentes y coincidencias opcionales.

Cada fuente identifica idFuente, ruta (relativa al manifiesto o absoluta) y sha256 del **archivo clasificado**. Se comprueban bytes, decisiones mediante recálculo, historial, vista, evaluación, URL original, intervalo y perfiles conocidos. Se contrastan ventanas observadas de axe y la emulación de Lighthouse, incluidas diferencias entre fuentes aunque el manifiesto no repita esos valores. El resto de condiciones físicas no se da por verificado por escribirlo en el manifiesto.

Los grupos permanecen separados; no se calculan medianas ni se elige una ejecución para ocultar otras. Una captura no puede incluirse dos veces cambiando el ID del lote. Las vistas sin fuentes y los indicadores sin observaciones siguen visibles.

### Coincidencias, incertidumbre y recomendaciones

No hay equivalencia automática por compartir indicador, selector o nombre de regla. Una coincidencia requiere:

- idCoincidencia, referencias a idFuente/idResultado e indiceNodo cuando corresponda a axe.
- elementoCanonico, problemaComun, responsable declarado, fechaHora con zona, fundamento y evidencia.
- Observaciones desfavorables del mismo indicador y grupo, de herramientas distintas. Métricas e incertidumbre no se fusionan.

El ejemplo muestra la forma exacta. Una declaración permite documentar XPath y CSS diferentes para un mismo elemento; el programa valida coherencia, no autentica esa identidad ni al revisor. Sin confirmación, los hallazgos permanecen separados.

La última revisión humana registrada determina el estado vigente; se conserva la decisión automática y no se inventa severidad después de revisar. Las recomendaciones enlazan hallazgo, observaciones, indicador, referencias y fuentes. Las incertidumbres reciben una solicitud de revisión. Las acciones de corrección/mejora son orientativas y deben comprobarse; no identifican causas del backend.

El orden técnico conserva prioridades observadas: crítica/alta/media/baja, fallos sin prioridad técnica, revisión y métricas intermedias. En cada nivel se consideran repetición de la misma comprobación bajo protocolo compatible, mínimo de elementos identificados y revisiones asociadas. Es una convención versionada del modelo, sin estimación de riesgo institucional.

### Salidas y límites

- diagnosticar produce JSON autocontenido: manifiesto, archivos clasificados íntegros y lotes originales, observaciones, cobertura, dimensiones, hallazgos, recomendaciones y límites.
- informe recalcula y verifica la integración desde los datos embebidos antes de producir Markdown. No necesita que sigan disponibles las rutas de entrada originales.
- El resumen entre vistas es descriptivo. Las diferencias de métricas requieren un protocolo de comparación explícito; no hay rankings.
- Los hashes comprueban coherencia, no autenticidad. El historial conserva enlaces a versiones previas; sin esos archivos no se verifica toda la cadena.
- No se crea un estado favorable por ausencia. P-06 sigue siendo contexto.
- La aplicación institucional, la evaluación DSR y las ejecuciones formales del plan DP mantienen sus procedimientos y evidencias propios.

### Archivos nuevos de esta etapa

- src/modelo_calidad_web/integracion/modelos.py: contratos de entrada y diagnóstico.
- src/modelo_calidad_web/integracion/motor.py: comprobación, agrupación y recomendaciones.
- src/modelo_calidad_web/integracion/informe.py: informe Markdown verificado.
- src/modelo_calidad_web/catalogos/reglas_integracion_v2.json: políticas y acciones vigentes (1.1.0); v1 conserva el historial.
- scripts/preparar_ejemplo_incremento_4.py: preparación reproducible del ejemplo simulado.
- datos/ejemplos/incremento_4/: entradas controladas y referencia.
- tests/test_integracion.py: integración, coherencia, errores y límites.

### Correcciones de auditoría 0.4.1

La versión 0.4.1 cierra los problemas técnicos reproducidos en la auditoría de los cuatro incrementos. El diagnóstico se regenera con reglas de integración **1.1.0** y un catálogo explícito de alcance por indicador. Los archivos de evidencia anteriores se conservan.

- La identidad de captura usa el objeto JSON canónico, además de conservar hashes de bytes. Reformatear un reporte no permite sumarlo otra vez.
- Se comprueban las dimensiones disponibles de axe y screenEmulation de Lighthouse contra el grupo y entre fuentes. Las condiciones físicas ausentes siguen siendo declaraciones.
- validar usa JSON estricto, rechaza claves repetidas y no finitos, y exige zona horaria.
- Los catálogos rechazan identificadores repetidos, campos obligatorios insuficientes y dimensiones inexistentes.
- Las nuevas clasificaciones embeben textoLoteImportado exacto. Se comprueba su huella y correspondencia con entradaImportada. Una salida histórica de tipo archivo sin ese texto se declara **no comprobada** para esa huella; sus decisiones sí se recalculan.
- Una revisión no puede preceder a la captura. Para una regla axe con varios nodos es obligatorio indicar alcance: nodo con indiceNodo entero, o resultado_completo. La revisión de un nodo no cambia los demás; se conserva el historial. Una revisión histórica multinodo sin alcance debe revisarse y documentarse expresamente; el programa no supone que cubrió todos.
- El diagnóstico incluye fichas técnicas de los veinte indicadores: fuente concreta, unidad, regla y límite real. A-09 no acredita todo el teclado, A-03 no cubre todos los campos y P-06 continúa contextual.

Ejemplo de revisión parcial (simulada; completar datos reales solo después de revisar):

~~~json
{
  "idResultado": "ID_DEL_RESULTADO",
  "alcance": "nodo",
  "indiceNodo": 0,
  "responsable": "REVISOR SIMULADO",
  "fechaHora": "2026-11-04T11:00:00-05:00",
  "estadoRevisado": "favorable",
  "fundamento": "SIMULADO: se revisó únicamente el nodo 0.",
  "evidencia": "EVIDENCIA SIMULADA DEL NODO 0"
}
~~~

Para preparar también una comparación controlada:

~~~powershell
.\.venv\Scripts\python.exe -B scripts/preparar_ejemplo_incremento_4.py --comparar --salida salidas/ejemplo_comparacion_041
.\.venv\Scripts\python.exe -B -m modelo_calidad_web diagnosticar salidas/ejemplo_comparacion_041/manifiesto.json --salida salidas/ejemplo_comparacion_041/diagnostico.json
.\.venv\Scripts\python.exe -B -m modelo_calidad_web informe salidas/ejemplo_comparacion_041/diagnostico.json --salida salidas/ejemplo_comparacion_041/informe.md
~~~

El campo opcional comparaciones del manifiesto requiere idComparacion, grupos de vistas diferentes, protocolo, responsable, fechaHora con zona, maxDiferenciaSegundos y condicionesComunes (navegador, red, cpu, ventanaAncho y ventanaAlto). El programa contrasta declaraciones entre grupos, perfiles, versiones, intervalo y configuración conservada. Solo muestra diferencias numéricas de una métrica si existe una medición admitida por grupo y configuraciones compatibles. Si faltan mediciones o hay varias capturas, se muestran todas sin promedio ni elección automática.

La frecuencia expresa vistas con la misma comprobación/estado bajo un protocolo compatible; no prueba que tengan la misma causa. Los conteos de elementos se presentan como mínimo identificable y máximo de ubicaciones, unidos solo por equivalencias documentadas. Los desempates consideran ese mínimo por indicador/estado dentro del grupo; no se suman dos evidencias como dos elementos confirmados.

**Compatibilidad:** importar/clasificar conservan sus perfiles anteriores; los manifiestos 0.4.0 se pueden volver a procesar. Los diagnósticos derivados 0.4.0 no se reinterpretan silenciosamente: informe pide regenerarlos desde su manifiesto con diagnosticar y una salida nueva. El catálogo de integración v1 y los informes anteriores permanecen como evidencia histórica. El catálogo vigente es reglas_integracion_v2.json (1.1.0), junto con alcance_indicadores_v1.json.

Estas correcciones no ejecutan la aplicación institucional, no completan automáticamente las fichas DP y no equivalen a evaluación DSR o validación experta.
