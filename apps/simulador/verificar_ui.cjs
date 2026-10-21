/* UI real con Playwright. No requiere red salvo el servidor local.
 * NODE_PATH debe resolver playwright; BASE_URL y QA_DIR son opcionales.
 */
const {chromium} = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
  const page = await browser.newPage({viewport:{width:1365,height:1000},colorScheme:"light"});
  const errores = [];
  page.setDefaultTimeout(10000);
  page.on("pageerror", e => errores.push(e.message));
  const base = process.env.BASE_URL || "http://127.0.0.1:8791";
  const qa = process.env.QA_DIR;
  if (qa) fs.mkdirSync(qa,{recursive:true});
  async function listo() {
    await page.getByRole("status").filter({hasText:"cálculo completo"}).waitFor();
  }
  async function configurar(cambios) {
    for(const [k,v] of Object.entries(cambios)) await page.locator('[name="'+k+'"]').fill(String(v));
    assert.equal(await page.locator("#results").isVisible(),false);
    await page.getByRole("button",{name:"Comparar escenario",exact:true}).click();
    await listo();
  }
  try {
    await page.goto(base);
    assert.match(await page.title(),/QuantileFlow · Simulador condicional/);
    await listo();
    assert.match(await page.locator("#winner").innerText(),/3 calls · K 103 \/ 14 días/);
    assert.match(await page.locator("#winner").innerText(),/148.35/);
    assert.equal(await page.locator("#ranking tbody tr").count(),10);
    if(qa) await page.screenshot({path:path.join(qa,"simulador-inicio.png")});
    await page.locator("#ranking tbody button").nth(1).click();
    assert.match(await page.locator("#selected-title").innerText(),/1 × K 100/);
    await page.locator("#ranking tbody button").first().click();
    assert.match(await page.locator("#selected-title").innerText(),/3 × K 103/);
    if(qa) await page.locator("#detail").screenshot({path:path.join(qa,"simulador-superficie.png")});
    const downloadPromise=page.waitForEvent("download");
    await page.getByRole("button",{name:"Descargar este escenario (.json)",exact:true}).click();
    const download=await downloadPromise;
    const exported=JSON.parse(fs.readFileSync(await download.path(),"utf8"));
    assert.equal(exported.configuracion.presupuesto,300);
    assert.equal(exported.mejor_objetivo.contrato,"C103-14d");
    await configurar({presupuesto:150});
    assert.doesNotMatch(await page.locator("#selected-title").innerText(),/^Explora 3 × K 103/);
    await configurar({presupuesto:300,dias:10});
    await page.getByRole("button",{name:"Explorar 3 calls, strike 103, 14 DTE",exact:true}).click();
    assert.match(await page.locator("#controls-text").innerText(),/ya venció/);
    await configurar({dias:61});
    assert.match(await page.locator("#winner").innerText(),/Conservar el efectivo/);
    assert.equal(await page.locator("#detail").isVisible(),false);
    await configurar({dias:7,riesgo_pct:0});
    assert.match(await page.locator("#winner").innerText(),/Conservar el efectivo/);
    await configurar({riesgo_pct:100,max_contratos:1});
    assert.equal(await page.locator("#ranking tbody tr").evaluateAll(rows=>
      rows.every(r=>r.cells[1].textContent==="1")),true);
    await page.locator('[name="cambio_iv_pp"]').fill("-25");
    await page.getByRole("button",{name:"Comparar escenario",exact:true}).click();
    await page.getByRole("alert").waitFor();
    assert.match(await page.getByRole("alert").innerText(),/IV de salida debe ser positiva/);
    assert.equal(await page.locator("#results").isVisible(),false);
    await configurar({cambio_iv_pp:0,max_contratos:0});
    for(const width of [375,320]){
      await page.setViewportSize({width,height:900});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
      await page.locator("#selected-title").scrollIntoViewIfNeeded();
      if(qa) await page.screenshot({path:path.join(qa,"simulador-movil-"+width+".png")});
    }
    assert.deepEqual(errores,[]);
    console.log("UI OK: cantidades, selección, descarga, vencimiento, efectivo, validación y móvil 375/320.");
  } catch(error) {
    console.error("Errores JS:",errores);
    console.error((await page.locator("body").innerText()).slice(0,5000));
    if(qa) await page.screenshot({path:path.join(qa,"fallo-ui.png")});
    throw error;
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
