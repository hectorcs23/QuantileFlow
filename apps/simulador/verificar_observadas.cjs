/* QA de la captura privada mediante Edge. No contiene cotizaciones. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'msedge'});
  const page=await browser.newPage({viewport:{width:1400,height:1000},colorScheme:'light'});
  const errores=[];page.on('pageerror',e=>errores.push(e.message));page.setDefaultTimeout(15000);
  const qa=process.env.QA_DIR;if(qa)fs.mkdirSync(qa,{recursive:true});
  try{
    await page.goto((process.env.BASE_URL||'http://127.0.0.1:8791')+'/observadas');
    await page.locator('#observadas-resultados').waitFor();
    assert.match(await page.locator('#foto-titulo').innerText(),/2026-10-22T0945/);
    assert.match(await page.locator('#dictamen').innerText(),/57 posiciones/);
    assert.match(await page.locator('#bloqueos').innerText(),/no son precios ejecutables/);
    assert.equal(await page.locator('#observada-posicion option').count(),57);
    assert.equal(await page.locator('#surface tbody tr').count(),8);
    await page.locator('#ab-resultados').waitFor();
    assert.equal(await page.locator('#ab-tabla tbody tr').count(),7);
    const downloadPromise=page.waitForEvent('download');await page.locator('#observadas-export').click();
    const exported=JSON.parse(fs.readFileSync(await(await downloadPromise).path(),'utf8'));
    assert.equal(exported.analisis.apto_compra,false);
    assert.equal(exported.analisis.embudo.presupuesto,57);
    assert.equal(exported.comparacion_ab.posiciones.length,2);
    const base=await page.locator('#surface tbody').innerText();
    await page.locator('#observada-iv').selectOption('0');
    assert.notEqual(await page.locator('#surface tbody').innerText(),base);
    if(qa)await page.locator('#observadas-explorar').screenshot({path:path.join(qa,'mapa-ui.png')});
    // Mismo contrato con cantidades distintas: selección válida y valores escalados.
    const choices=exported.analisis.posiciones;const index=choices.findIndex(p=>p.max_cantidad>=2);
    assert.ok(index>=0);
    await page.locator('#observada-a').selectOption(String(index));await page.locator('#n-a').fill('1');
    await page.locator('#observada-b').selectOption(String(index));await page.locator('#n-b').fill('2');
    assert.equal(await page.locator('#ab-resultados').isVisible(),false);
    await page.getByRole('button',{name:'Comparar compras observadas',exact:true}).click();await page.locator('#ab-resultados').waitFor();
    const d2=page.waitForEvent('download');await page.locator('#observadas-export').click();
    const ab=JSON.parse(fs.readFileSync(await(await d2).path(),'utf8')).comparacion_ab;
    assert.equal(ab.posiciones[0].cantidad,1);assert.equal(ab.posiciones[1].cantidad,2);
    assert.ok(Math.abs(ab.posiciones[1].controles[0].nominal-2*ab.posiciones[0].controles[0].nominal)<1e-7);
    // Un cambio invalida la comparación y la descarga no preserva resultados viejos.
    await page.locator('[name="presupuesto"]').fill('1');assert.equal(await page.locator('#observadas-resultados').isVisible(),false);
    await page.getByRole('button',{name:'Evaluar captura',exact:true}).click();await page.locator('#observadas-resultados').waitFor();
    assert.match(await page.locator('#dictamen').innerText(),/No hay candidatos/);
    assert.equal(await page.locator('#observadas-duelo').isVisible(),false);
    await page.locator('[name="presupuesto"]').fill('300');await page.getByRole('button',{name:'Evaluar captura',exact:true}).click();await page.locator('#observadas-resultados').waitFor();
    for(const width of [375,320]){
      await page.setViewportSize({width,height:900});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      if(qa)await page.screenshot({path:path.join(qa,'movil-'+width+'.png')});
    }
    assert.deepEqual(errores,[]);console.log('UI observada OK: captura, 57 compras, A/B exacto, mapas, exportación, ausencia, invalidación y móvil.');
  }catch(e){console.error(e);process.exitCode=1;}finally{await browser.close();}
})();
