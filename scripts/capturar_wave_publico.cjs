// Ejecución reproducible de la extensión WAVE sobre la demo pública W3C.
// Requiere WAVE_EXTENSION_DIR, PLAYWRIGHT_BROWSERS_PATH y paquetes en .tools.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { chromium } = require('../.tools/node_modules/playwright-core');

const url = 'https://www.w3.org/WAI/demos/bad/before/home.html';
const extension = process.env.WAVE_EXTENSION_DIR;
const salida = path.resolve(process.env.SALIDA_MUESTRAS || 'datos/muestras_publicas');
if (!extension || !fs.existsSync(path.join(extension, 'manifest.json'))) {
  throw new Error('WAVE_EXTENSION_DIR debe apuntar a la carpeta de una extensión WAVE instalada');
}

(async () => {
  const context = await chromium.launchPersistentContext(path.resolve('.tools/profile-wave-publico'), {
    channel: 'chromium', headless: true,
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  try {
    const page = await context.newPage();
    const respuesta = await page.goto(url, {waitUntil:'domcontentloaded', timeout:45000});
    if (respuesta?.status() !== 200) throw new Error(`HTTP ${respuesta?.status()}`);
    const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker', {timeout:15000});
    await worker.evaluate(async targetUrl => {
      const tabs = await chrome.tabs.query({url:targetUrl});
      if (!tabs[0]) throw new Error('La pestaña pública no está disponible para WAVE');
      await serviceworker.func.runWave(tabs[0].id, targetUrl);
    }, url);
    await page.waitForFunction(() => window.wave?.results?.success === true, {timeout:30000});
    const capturadoEn = new Date().toISOString();
    const {version, resultado} = await page.evaluate(() => ({version:wave.version, resultado:JSON.stringify(wave.results)}));
    fs.mkdirSync(salida, {recursive:true});
    fs.writeFileSync(path.join(salida, 'wave_extension_raw.json'), resultado, 'utf8');
    await page.waitForTimeout(2000);
    await page.screenshot({path:path.join(salida, 'wave_extension_pantalla.png')});
    const manifiesto = {
      procedimiento:'scripts/capturar_wave_publico.cjs: Chromium persistente, extensión WAVE, serviceworker.func.runWave, lectura wave.results',
      urlSolicitada:url, urlFinal:page.url(), httpStatus:respuesta.status(),
      extensionId:new URL(worker.url()).hostname, extensionVersion:version,
      playwrightVersion:require('../.tools/node_modules/playwright-core/package.json').version,
      browserVersion:context.browser().version(), capturadoEn,
      sha256Fuente:crypto.createHash('sha256').update(resultado).digest('hex'),
    };
    fs.writeFileSync(path.join(salida, 'wave_procedimiento.json'), JSON.stringify(manifiesto,null,2)+'\n');
    console.log(JSON.stringify({version, estadisticas:JSON.parse(resultado).statistics, manifiesto},null,2));
  } finally { await context.close(); }
})().catch(error => {console.error(error); process.exitCode=1;});
