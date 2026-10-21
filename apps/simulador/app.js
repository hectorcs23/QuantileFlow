"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const form = $("inputs");
  const usd = new Intl.NumberFormat("es-MX", {style:"currency", currency:"USD", maximumFractionDigits:2});
  const signed = new Intl.NumberFormat("es-MX", {style:"currency", currency:"USD", maximumFractionDigits:2, signDisplay:"always"});
  const num = new Intl.NumberFormat("es-MX", {maximumFractionDigits:2});
  let result = null, selected = null, sequence = 0, controller = null;
  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  const money = v => usd.format(v);
  const pnl = v => signed.format(v);
  const position = () => result?.posiciones.find(p => p.contrato === selected);
  const label = p => "K "+num.format(p.strike)+" / "+p.dte+" días";
  function metric(title, value, detail) {
    const box = el("div", undefined, "metric");
    box.append(el("p", title), el("strong", value));
    if (detail) box.append(el("small", detail));
    return box;
  }
  function clearResults(message) {
    result = null; selected = null;
    $("results").hidden = true; $("error").hidden = true;
    $("status").textContent = message;
  }
  form.addEventListener("input", () => {
    sequence++; controller?.abort();
    form.querySelector("button[type=submit]").disabled = false;
    clearResults("Parámetros modificados. Pulsa «Comparar escenario» para recalcular.");
  });
  async function calculate(event) {
    event?.preventDefault();
    if (!form.reportValidity()) return;
    const ticket = ++sequence;
    controller?.abort();
    controller = new AbortController();
    const cfg = Object.fromEntries([...new FormData(form)].map(([k,v]) => [k, Number(v)]));
    clearResults("Calculando posiciones y escenarios…");
    form.querySelector("button[type=submit]").disabled = true;
    try {
      const response = await fetch("/api/simular", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify(cfg), signal:controller.signal
      });
      const data = await response.json();
      if (ticket !== sequence) return;
      if (!response.ok) throw new Error(data.error || "Error de cálculo");
      result = data;
      selected = data.posiciones[0]?.contrato || null;
      render();
      $("status").textContent = data.posiciones.length+" alternativas elegibles · datos sintéticos · cálculo completo";
    } catch (err) {
      if (ticket !== sequence || err.name === "AbortError") return;
      clearResults("No se muestran resultados con estos parámetros.");
      $("error").textContent = err.message;
      $("error").hidden = false;
    } finally {
      if (ticket === sequence) form.querySelector("button[type=submit]").disabled = false;
    }
  }
  form.addEventListener("submit", calculate);
  function render() {
    $("results").hidden = false;
    const best = result.mejor_objetivo, cfg = result.configuracion;
    const chosen = result.posiciones.find(p => p.contrato === best.contrato);
    const winner = $("winner"); winner.replaceChildren();
    winner.append(el("p", chosen
      ? chosen.cantidad+" "+(chosen.cantidad === 1 ? "call" : "calls")+" · "+label(chosen)
      : "Conservar el efectivo", "headline"));
    const metrics = el("div", undefined, "metrics");
    metrics.append(
      metric("Ganancia / pérdida neta", pnl(best.pnl), num.format(cfg.movimiento_pct)+"% en "+cfg.dias+" días; IV "+num.format(cfg.iv_pct+cfg.cambio_iv_pp)+"%"),
      metric("Capital final, incluida la caja", money(cfg.presupuesto+best.pnl), "Inicial: "+money(cfg.presupuesto)),
      metric("Pérdida máxima con costos", money(chosen?.perdida_maxima_costos_asumidos || 0), chosen ? "Puede perderse todo el capital reservado" : "Efectivo sin intereses"));
    winner.append(metrics);
    const tbody = $("ranking").querySelector("tbody"); tbody.replaceChildren();
    for (const p of result.posiciones) {
      const tr = el("tr"); tr.dataset.contract = p.contrato;
      const td = el("td"), button = el("button", label(p));
      button.type = "button";
      button.setAttribute("aria-label", "Explorar "+p.cantidad+" calls, strike "+num.format(p.strike)+", "+p.dte+" DTE");
      button.addEventListener("click", () => {selected=p.contrato; renderDetail();});
      td.append(button); tr.append(td);
      for (const value of [String(p.cantidad), money(p.prima_por_contrato),
                          money(p.capital_reservado), money(p.efectivo_libre), pnl(p.pnl_objetivo)]) tr.append(el("td", value));
      tr.lastChild.className = p.pnl_objetivo >= 0 ? "pos" : "neg";
      tbody.append(tr);
    }
    if (!result.posiciones.length) {
      const td = el("td", "Ninguna opción cumple el plazo y los límites. El efectivo sigue disponible.");
      td.colSpan=6; const tr=el("tr"); tr.append(td); tbody.append(tr);
    }
    const list = $("exclusions").querySelector("ul"); list.replaceChildren();
    result.excluidos.forEach(e => {
      const c = result.cadena.find(c => c.identificador === e.contrato) || e;
      list.append(el("li", label(c)+": "+e.motivo));
    });
    $("exclusions").querySelector("summary").textContent = "Contratos excluidos ("+result.excluidos.length+")";
    $("exclusions").open = !result.posiciones.length;
    renderNeighbors(); renderDetail();
  }
  function renderNeighbors() {
    const v = result.vecindad, table = $("neighbors");
    const head = el("tr"); head.append(el("th", "Plazo / movimiento"));
    v.movimientos_pct.forEach(m => head.append(el("th", num.format(m)+"%")));
    table.querySelector("thead").replaceChildren(head);
    table.querySelector("tbody").replaceChildren();
    v.plazos_dias.forEach((d,i) => {
      const row = el("tr"); row.append(el("th", d+" días"));
      v.mejores[i].forEach(w => {
        const c = result.cadena.find(c => c.identificador === w.contrato);
        const td = el("td", c ? w.cantidad+" × "+label(c) : "Efectivo");
        td.append(el("small", pnl(w.pnl)));
        row.append(td);
      });
      table.querySelector("tbody").append(row);
    });
  }
  function renderDetail() {
    const p = position(); $("detail").hidden = !p;
    for (const row of $("ranking").querySelectorAll("tbody tr[data-contract]")) {
      const active = row.dataset.contract === selected;
      row.classList.toggle("selected", active);
      row.querySelector("button").setAttribute("aria-pressed", String(active));
    }
    if (!p) return;
    $("selected-title").textContent = "Explora "+p.cantidad+" × "+label(p);
    $("position-metrics").replaceChildren(
      metric("Capital reservado", money(p.capital_reservado), "Entrada "+money(p.desembolso)+" + reserva de cierre "+money(p.reserva_cierre)),
      metric("Efectivo libre", money(p.efectivo_libre), "Permanece fuera de la posición"),
      metric("Ganancia / pérdida objetivo", pnl(p.pnl_objetivo), num.format(100*p.retorno_presupuesto)+"% del presupuesto total"));
    const axes = result.ejes, surface = $("surface");
    const head = el("tr"); head.append(el("th", "Días / cambio"));
    axes.movimientos_pct.forEach(m => head.append(el("th", num.format(m)+"%")));
    surface.querySelector("thead").replaceChildren(head); surface.querySelector("tbody").replaceChildren();
    axes.plazos_dias.forEach((d,i) => {
      const row = el("tr"); const th=el("th", d+" d"); th.scope="row"; row.append(th);
      p.pnl_por_plazo_movimiento[i].forEach((v,j) => {
        const cell = el("td", v === null ? "—" : pnl(v), v === null ? "unavailable" : v >= 0 ? "positive" : "negative");
        cell.title = v === null ? "Ya venció; se necesita el precio al vencimiento" : d+" días, "+axes.movimientos_pct[j]+"%: "+pnl(v);
        row.append(cell);
      });
      surface.querySelector("tbody").append(row);
    });
    $("surface-caption").textContent = "Mismos "+p.cantidad+" contratos y entrada de "+money(p.desembolso)+". Cambio de IV fijo: "+num.format(result.configuracion.cambio_iv_pp)+" puntos.";
    const names = {delta:"Delta · USD por +US$1 del subyacente", gamma:"Gamma · cambio de delta por +US$1", vega_por_punto_iv:"Vega · USD por +1 punto de IV", theta_por_dia:"Theta · USD por día transcurrido"};
    $("greeks").replaceChildren(...Object.entries(p.sensibilidad_posicion).map(([k,v]) => el("p", names[k]+": "+num.format(v))));
    requestAnimationFrame(drawCharts);
  }
  function svgElement(tag, attrs={}, text) {
    const n = document.createElementNS("http://www.w3.org/2000/svg",tag);
    for (const [k,v] of Object.entries(attrs)) n.setAttribute(k,String(v));
    if (text !== undefined) n.textContent=text;
    return n;
  }
  function drawCharts() {
    const p=position(); if(!p || $("results").hidden) return;
    const names={objetivo:"Tu objetivo",sin_movimiento:"No se mueve",baja_3_pct:"Baja 3%",iv_menos_5_pp:"IV cae 5 puntos más",siete_dias_tarde:"Llega 7 días tarde"};
    const svg=$("controls-chart"), w=svg.getBoundingClientRect().width;
    if(w<1) return;
    const vals=p.controles.filter(c=>c.pnl!==null).map(c=>c.pnl);
    const lo=Math.min(0,...vals), hi=Math.max(0,...vals), range=(hi-lo)||1;
    const x=v=>8+(w-16)*(v-lo)/range, zero=x(0);
    svg.replaceChildren(); svg.setAttribute("height","340"); svg.setAttribute("viewBox","0 0 "+w+" 340");
    svg.append(svgElement("title",{},"Escenarios para "+p.cantidad+" calls, "+label(p)));
    p.controles.forEach((c,i)=>{
      const y=20+i*56;
      svg.append(svgElement("text",{x:0,y},names[c.nombre]));
      svg.append(svgElement("text",{x:w,y,"text-anchor":"end"}, c.pnl===null ? (c.motivo.startsWith("ya venció")?"Ya venció":"IV inválida") : pnl(c.pnl)));
      if(c.pnl!==null) {
        const bar=svgElement("rect",{x:Math.min(zero,x(c.pnl)),y:y+10,width:Math.max(1,Math.abs(x(c.pnl)-zero)),height:14,fill:c.pnl>=0?"var(--blue)":"var(--orange)"});
        bar.append(svgElement("title",{},names[c.nombre]+": "+pnl(c.pnl))); svg.append(bar);
        svg.append(svgElement("line",{x1:zero,y1:y+7,x2:zero,y2:y+27,stroke:"var(--muted)","stroke-width":1}));
      }
    });
    svg.append(svgElement("text",{x:8,y:315},money(lo)));
    svg.append(svgElement("text",{x:w-8,y:315,"text-anchor":"end"},money(hi)));
    svg.append(svgElement("text",{x:w/2,y:337,"text-anchor":"middle"},"Ganancia / pérdida neta, USD"));
    $("controls-text").textContent=p.controles.map(c=>names[c.nombre]+": "+(c.pnl===null?c.motivo:pnl(c.pnl))).join("; ");
    drawIV(p);
  }
  function drawIV(p) {
    const svg=$("iv-chart"), w=svg.getBoundingClientRect().width, h=270;
    const xs=result.ejes.choques_iv_pp;
    const values=p.pnl_por_iv.filter(v=>v!==null);
    const lo=Math.min(0,...values), hi=Math.max(0,...values), span=hi-lo||1;
    const ymin=lo-span*.12, ymax=hi+span*.12;
    const left=66,right=w-12,top=20,bottom=213;
    const x=v=>left+(right-left)*(v-xs[0])/(xs.at(-1)-xs[0]);
    const y=v=>bottom-(bottom-top)*(v-ymin)/(ymax-ymin);
    svg.replaceChildren();svg.setAttribute("height",h);svg.setAttribute("viewBox","0 0 "+w+" "+h);
    svg.append(svgElement("title",{},"Ganancia o pérdida neta según el cambio de IV"));
    [lo,(hi+lo)/2,hi].filter((v,i,a)=>a.indexOf(v)===i).forEach(v=>{
      svg.append(svgElement("line",{x1:left,y1:y(v),x2:right,y2:y(v),class:"axis"}));
      svg.append(svgElement("text",{x:left-8,y:y(v)+4,"text-anchor":"end"},num.format(Math.round(v))));
    });
    svg.append(svgElement("text",{x:0,y:13},"PnL, USD"));
    svg.append(svgElement("line",{x1:left,y1:y(0),x2:right,y2:y(0),stroke:"var(--muted)","stroke-width":1}));
    let path="", segment=false;
    p.pnl_por_iv.forEach((v,i)=>{
      if(v===null){segment=false;return;}
      path+=(segment?"L":"M")+x(xs[i])+","+y(v)+" ";segment=true;
    });
    svg.append(svgElement("path",{d:path,stroke:"var(--blue)","stroke-width":2,fill:"none"}));
    let lastTick=-Infinity;
    xs.forEach((v,i)=>{
      if(i===xs.length-1 || (x(v)-lastTick>=35 && (i===0 || right-x(v)>=35))) {
        svg.append(svgElement("text",{x:x(v),y:236,"text-anchor":"middle"},String(v)));
        lastTick=x(v);
      }
      if(p.pnl_por_iv[i]===null)return;
      const dot=svgElement("circle",{cx:x(v),cy:y(p.pnl_por_iv[i]),r:4,fill:"var(--blue)"});
      dot.append(svgElement("title",{},v+" puntos de IV: "+pnl(p.pnl_por_iv[i])));svg.append(dot);
    });
    svg.append(svgElement("text",{x:(left+right)/2,y:264,"text-anchor":"middle"},"Cambio de IV, puntos porcentuales"));
    $("iv-text").textContent=xs.map((v,i)=>v+" puntos: "+(p.pnl_por_iv[i]===null?"IV inválida":pnl(p.pnl_por_iv[i]))).join("; ");
  }
  $("export").addEventListener("click",()=>{
    if(!result)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)+"\n"],{type:"application/json"}));
    const a=el("a");a.href=url;a.download="quantileflow-escenario-sintetico.json";
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  new ResizeObserver(()=>requestAnimationFrame(drawCharts)).observe(document.querySelector(".content"));
  calculate();
})();
