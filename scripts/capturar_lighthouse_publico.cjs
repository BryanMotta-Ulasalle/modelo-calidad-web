// Ejecuta Lighthouse y conserva su LHR original sobre la demo pública W3C.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const {spawnSync} = require('child_process');

const url = 'https://www.w3.org/WAI/demos/bad/before/home.html';
const salida = path.resolve(process.env.SALIDA_MUESTRAS || 'datos/muestras_publicas');
const chrome = process.env.CHROME_PATH;
if (!chrome || !fs.existsSync(chrome)) throw new Error('CHROME_PATH debe apuntar a Chrome instalado');
fs.mkdirSync(salida,{recursive:true});
const destino = path.join(salida,'lighthouse_result_raw.json');
const cli = path.resolve('.tools/node_modules/lighthouse/cli/index.js');
const argumentos = [cli,url,'--output=json',`--output-path=${destino}`,'--only-categories=performance',
  '--chrome-flags=--headless=new --no-first-run --disable-gpu','--quiet'];
const proceso = spawnSync(process.execPath,argumentos,{stdio:'inherit',timeout:180000,env:process.env});
if (proceso.error || proceso.status !== 0) throw proceso.error || new Error(`Lighthouse terminó con ${proceso.status}`);
const bytes = fs.readFileSync(destino);
const lhr = JSON.parse(bytes.toString('utf8'));
const manifiesto = {
  procedimiento:'scripts/capturar_lighthouse_publico.cjs: CLI Lighthouse con Chrome headless y solo categoría performance',
  urlSolicitada:url, urlFinal:lhr.finalDisplayedUrl, lighthouseVersion:lhr.lighthouseVersion,
  chromePathTipo:'CHROME_PATH provisto por el operador',
  versionPaquete:require('../.tools/node_modules/lighthouse/package.json').version,
  comandoArgumentos:argumentos.slice(1).map(arg=>arg.replace(destino,'<archivo-salida>')),
  codigoSalida:proceso.status,
  sha256Fuente:crypto.createHash('sha256').update(bytes).digest('hex'),
};
fs.writeFileSync(path.join(salida,'lighthouse_procedimiento.json'),JSON.stringify(manifiesto,null,2)+'\n');
console.log(JSON.stringify({auditorias:Object.keys(lhr.audits).length,metricas:lhr.categories.performance.auditRefs.filter(ref=>ref.group==='metrics').length,manifiesto},null,2));
