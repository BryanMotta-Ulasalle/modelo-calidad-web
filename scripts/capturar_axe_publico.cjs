// Ejecución comprobable: Playwright invoca axe-core en la demo pública W3C.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { chromium } = require('../.tools/node_modules/playwright-core');
const axe = require('../.tools/node_modules/axe-core');

const url = 'https://www.w3.org/WAI/demos/bad/before/home.html';
const salida = path.resolve(process.env.SALIDA_MUESTRAS || 'datos/muestras_publicas');

(async () => {
  const navegador = await chromium.launch({channel:'chromium', headless:true});
  try {
    const pagina = await navegador.newPage();
    const respuesta = await pagina.goto(url, {waitUntil:'domcontentloaded', timeout:45000});
    if (respuesta?.status() !== 200) throw new Error(`HTTP ${respuesta?.status()}`);
    await pagina.addScriptTag({content:axe.source});
    const resultado = await pagina.evaluate(async () => window.axe.run(document));
    const texto = JSON.stringify(resultado,null,2)+'\n';
    fs.mkdirSync(salida, {recursive:true});
    fs.writeFileSync(path.join(salida,'axe_core_raw.json'),texto,'utf8');
    const manifiesto = {
      procedimiento:'scripts/capturar_axe_publico.cjs: playwright-core -> Chromium -> page.goto -> addScriptTag(axe.source) -> page.evaluate(axe.run)',
      urlSolicitada:url, urlFinal:pagina.url(), httpStatus:respuesta.status(),
      playwrightVersion:require('../.tools/node_modules/playwright-core/package.json').version,
      axePackageVersion:axe.version, browserVersion:navegador.version(),
      testEngine:resultado.testEngine, testRunner:resultado.testRunner,
      sha256Fuente:crypto.createHash('sha256').update(texto).digest('hex'),
    };
    fs.writeFileSync(path.join(salida,'axe_procedimiento.json'),JSON.stringify(manifiesto,null,2)+'\n');
    console.log(JSON.stringify({grupos:Object.fromEntries(['violations','incomplete','passes','inapplicable'].map(clave=>[clave,resultado[clave].length])),manifiesto},null,2));
  } finally {await navegador.close();}
})().catch(error => {console.error(error); process.exitCode=1;});
