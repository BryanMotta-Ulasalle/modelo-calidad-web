// Captura pública para comprobar contratos concretos. No evalúa el portal institucional.
// Requiere .tools con playwright-core 1.63.0, axe-core 4.14.0,
// lighthouse 13.5.0 y lighthouse-legacy (alias de lighthouse 12.8.2).
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const {spawnSync} = require('child_process');
const {chromium} = require('../.tools/node_modules/playwright-core');
const axe = require('../.tools/node_modules/axe-core');

const url = process.env.URL_MUESTRA || 'https://www.w3.org/WAI/demos/bad/before/home.html';
if (!['https://www.w3.org/WAI/demos/bad/before/home.html', 'https://example.com/'].includes(url)) {
  throw new Error('La captura está limitada a las dos páginas públicas documentadas');
}
const salida = path.resolve(process.env.SALIDA_MUESTRAS || 'datos/muestras_publicas_incremento3');
const mapas = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../src/modelo_calidad_web/catalogos/mapeos_fuentes_v2.json')));
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function guardar(nombre, datos) {
  const texto = JSON.stringify(datos, null, 2) + '\n';
  fs.writeFileSync(path.join(salida, nombre), texto, {encoding: 'utf8', flag: 'wx'});
  return sha(texto);
}

(async () => {
  // Una carpeta nueva evita reemplazar evidencia anterior.
  fs.mkdirSync(salida);
  const navegador = await chromium.launch({channel: 'chrome', headless: true});
  try {
    const pagina = await navegador.newPage();
    const respuesta = await pagina.goto(url, {waitUntil: 'networkidle', timeout: 60000});
    if (respuesta?.status() !== 200) throw new Error(`HTTP ${respuesta?.status()}`);
    await pagina.addScriptTag({content: axe.source});
    const reglas = Object.keys(mapas.mapeos['axe-core-playwright']);
    const resultado = await pagina.evaluate(async ids => window.axe.run(document, {runOnly: {type: 'rule', values: ids}}), reglas);
    const hash = guardar('axe_core_raw.json', resultado);
    guardar('axe_procedimiento.json', {
      procedimiento: 'scripts/capturar_incremento_3.cjs: Chrome por Playwright -> axe.run; runOnly explícito de IDs mapeados',
      urlSolicitada: url, urlFinal: pagina.url(), httpStatus: respuesta.status(),
      playwrightVersion: require('../.tools/node_modules/playwright-core/package.json').version,
      browserVersion: navegador.version(), testEngine: resultado.testEngine, testRunner: resultado.testRunner,
      reglasSolicitadas: reglas, sha256Fuente: hash,
    });
  } finally { await navegador.close(); }

  const auditorias = [
    'first-contentful-paint', 'largest-contentful-paint', 'total-blocking-time',
    'cumulative-layout-shift', 'speed-index', 'paste-preventing-inputs', 'errors-in-console',
    'http-status-code', 'document-title',
  ];
  for (const [paquete, nombre, extras] of [
    ['lighthouse-legacy', 'lighthouse_12', ['viewport']],
    ['lighthouse', 'lighthouse_13', []],
  ]) {
    const destino = path.join(salida, nombre + '_raw.json');
    if (fs.existsSync(destino)) throw new Error('Salida existente: ' + destino);
    const cli = path.resolve(__dirname, '../.tools/node_modules/' + paquete + '/cli/index.js');
    const args = [cli, url, '--output=json', '--output-path=' + destino,
      '--only-audits=' + [...auditorias, ...extras].join(','),
      '--chrome-flags=--headless=new --no-first-run --disable-gpu', '--quiet'];
    const proceso = spawnSync(process.execPath, args, {stdio: 'inherit', timeout: 240000, env: process.env});
    if (proceso.error || proceso.status !== 0) throw proceso.error || new Error('Lighthouse: ' + proceso.status);
    const bytes = fs.readFileSync(destino);
    const lhr = JSON.parse(bytes.toString('utf8'));
    if (lhr.runtimeError) throw new Error(JSON.stringify(lhr.runtimeError));
    guardar(nombre + '_procedimiento.json', {
      procedimiento: 'scripts/capturar_incremento_3.cjs: Lighthouse CLI con auditorías explícitas; versión fijada por alias local',
      urlSolicitada: url, urlFinal: lhr.finalDisplayedUrl, lighthouseVersion: lhr.lighthouseVersion,
      argumentos: args.slice(1).map(arg => arg.replace(destino, '<salida>')),
      fechaCaptura: lhr.fetchTime, codigoSalida: proceso.status, sha256Fuente: sha(bytes),
      estadoHttpObservado: lhr.audits['http-status-code']?.score,
      documentoTitulo: lhr.audits['document-title']?.score,
    });
    if (lhr.audits['http-status-code']?.score !== 1) throw new Error('Documento principal sin HTTP satisfactorio: conservar como intento, no como demostración del sitio');
  }
  console.log(JSON.stringify({salida, archivos: fs.readdirSync(salida)}, null, 2));
})().catch(error => {console.error(error); process.exitCode = 1;});
