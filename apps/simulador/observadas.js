'use strict';
(() => {
  const $=s=>document.querySelector(s), form=$('#observadas-form');
  const fmt=v=>v===null?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  const names={objetivo:'Objetivo',mitad:'Mitad del movimiento',sin_movimiento:'Sin movimiento',baja_3:'Baja 3%',iv_menor:'IV cae 5 puntos más',tarde:'Llega 7 días tarde',combinado:'Mitad, tarde e IV menor'};
  let data=null, ab=null, request=null, abRequest=null, generation=0;
  function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
  function cfg(){return Object.fromEntries([...new FormData(form)].map(([k,v])=>[k,Number(v)]));}
  function invalidate(){generation++;request?.abort();abRequest?.abort();data=ab=null;$('#observadas-resultados').hidden=true;$('#ab-resultados').hidden=true;$('#status').textContent='Parámetros cambiados. Evalúa de nuevo la captura.';}
  form.addEventListener('input',invalidate);
  const label=p=>`${p.cantidad} × K ${p.strike} / ${p.dte.toFixed(2)} DTE`;
  function options(el,items){el.replaceChildren(...items.map(([value,text])=>{const o=node('option',text);o.value=value;return o;}));}
  function winner(result,indices){if(indices===null)return 'Sin comparar: falta valoración';return indices.map(i=>i==='efectivo'?'Efectivo':label(result.posiciones[Number(i)])).join(' / ');}
  function value(c){return `${fmt(c.nominal)} [${fmt(c.inferior)}, ${fmt(c.superior)}]`;}
  function selectMap(){
    const p=data.posiciones[Number($('#observada-posicion').value)], j=Number($('#observada-iv').value), m=p.mapas[j], e=data.ejes;
    $('#posicion-resumen').textContent=`${label(p)}. Capital reservado: ${fmt(p.capital_reservado)} USD; efectivo libre: ${fmt(p.efectivo_libre)} USD. IV inicial: ${fmt(p.iv_pct)}%.`;
    const tr=node('tr');tr.append(node('th','Días / cambio'));e.movimientos_pct.forEach(x=>tr.append(node('th',x+'%')));$('#surface thead').replaceChildren(tr);
    $('#surface tbody').replaceChildren(...e.plazos_dias.map((d,i)=>{const tr=node('tr');tr.append(node('th',String(d)));e.movimientos_pct.forEach((_,k)=>{const v=m.nominal[i][k],td=node('td',fmt(v),v===null?'unavailable':v>=0?'positive':'negative');td.title=`Banda de supuestos: ${fmt(m.inferior[i][k])} a ${fmt(m.superior[i][k])} USD`;tr.append(td);});return tr;}));
  }
  function quantities(side){const p=data.posiciones[Number($('#observada-'+side).value)],input=$('#n-'+side);input.max=p.max_cantidad;input.value=Math.min(p.max_cantidad,side==='a'?3:1);}
  function invalidateAB() {abRequest?.abort();ab=null;$('#ab-resultados').hidden=true;$('#ab-status').textContent='Selección cambiada. Compara de nuevo.';}
  async function compareAB(event){event?.preventDefault();if(!data||!$('#observadas-ab').reportValidity())return;invalidateAB();const gen=generation;abRequest=new AbortController();const signal=abRequest.signal;
    const alternativas=['a','b'].map(side=>({contrato:data.posiciones[Number($('#observada-'+side).value)].contrato,cantidad:Number($('#n-'+side).value)}));
    $('#ab-status').textContent='Calculando compras…';
    try{const res=await fetch('/api/observadas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({configuracion:data.configuracion,alternativas}),signal});const r=await res.json();if(!res.ok)throw Error(r.error);if(gen!==generation||signal.aborted)return;ab=r;
      $('#ab-capital').textContent=r.posiciones.map((p,i)=>`${'AB'[i]}: ${label(p)}, reservado ${fmt(p.capital_reservado)} USD, libre ${fmt(p.efectivo_libre)} USD`).join(' · ');
      $('#ab-tabla tbody').replaceChildren(...r.posiciones[0].controles.map((c,k)=>{const tr=node('tr');tr.append(node('th',names[c.nombre]),node('td',value(c)),node('td',value(r.posiciones[1].controles[k])),node('td',r.mejores_nominales[k]===null?'Sin comparar':r.mejores_nominales[k].map(x=>x==='efectivo'?'Efectivo':'AB'[Number(x)]).join(' / ')));return tr;}));
      $('#ab-resultados').hidden=false;$('#ab-status').textContent='Comparación calculada; siguen vigentes los bloqueos de calidad.';
    }catch(e){if(e.name!=='AbortError')$('#ab-status').textContent=e.message;}
  }
  function render(r){
    const spy=r.subyacente==='SPY', raiz=spy?'SPY':'SPXW', otra=spy?'SPXW':'SPY', div=r.dividendos;
    $('#foto-titulo').textContent=`Captura ${r.captura} · ${raiz} · exploratoria`;
    $('#instrumento').textContent=spy?'SPY americano. SPXW se cuenta en el diagnóstico, pero no se valora en este modo.':'SPXW europeo PM. SPY se cuenta en el diagnóstico, pero no se valora en este modo.';
    $('#embudo').replaceChildren(...[['Calls observados',r.embudo.calls],[raiz+' con calidad básica',r.embudo.calidad],['Caben y cubren el plazo',r.embudo.presupuesto]].map(([k,v])=>{const d=node('div',undefined,'metric');d.append(node('p',k),node('strong',String(v)));return d;}));
    $('#dictamen').textContent=r.posiciones.length?`${r.posiciones.length} posiciones calculables. Ninguna habilitada como recomendación de compra.`:'No hay candidatos que cumplan presupuesto, plazo y calidad. No se fabrica una elección.';
    $('#bloqueos').replaceChildren(...r.bloqueos.map(x=>node('li',x)));$('#alcance').replaceChildren(...r.alcance.map(x=>node('li',x)));
    $('#reglas').textContent=`Edad máxima: ${r.reglas.edad_maxima_s} s. Spread relativo máximo: ${r.reglas.spread_relativo_max*100}%. Tamaño mínimo: 1. ${spy?`Tasa 4%, supuesta. Dividendos conocidos al corte: ${div.conocidos_al_corte}; declarados por venir: ${div.declarados_futuros.length}. No se valora lo que vence desde ${div.primera_fecha_ex_sin_declarar??'ninguna fecha: falta historial'}: podría cruzar un dividendo sin declarar.`:'Tasa 4%, dividendo continuo 1.3%, supuestos.'} ${otra}: ${r.inventario[otra]?.calls||0} calls observados; no se valoran en este modo.`;
    $('#observadas-explorar').hidden=$('#observadas-duelo').hidden=!r.posiciones.length;
    if(r.posiciones.length){
      const sorted=r.posiciones.map((p,i)=>[i,p]).sort((a,b)=>(b[1].controles[0].nominal??-Infinity)-(a[1].controles[0].nominal??-Infinity));
      options($('#observada-posicion'),sorted.map(([i,p])=>[i,label(p)]));
      options($('#observada-iv'),r.ejes.choques_iv_pp.map((x,i)=>[i,(x>0?'+':'')+x+' puntos de IV']));$('#observada-iv').value='1';selectMap();
      for(const side of ['a','b'])options($('#observada-'+side),sorted.map(([i,p])=>[i,`K ${p.strike} / ${p.dte.toFixed(2)} DTE · máximo ${p.max_cantidad}`]));
      $('#observada-b').value=String(sorted[Math.min(1,sorted.length-1)][0]);quantities('a');quantities('b');compareAB();
    }
    const filas=r.posiciones[0]?.controles||[];
    $('#escenarios-observados tbody').replaceChildren(...filas.map((c,k)=>{const tr=node('tr');tr.append(node('th',names[c.nombre]),node('td',winner(r,r.mejores_nominales[k])),node('td',r.separados_banda[k].length?'Una posición supera todas las bandas rivales y efectivo':'Sin ganador separado'));return tr;}));
    $('#estabilidad').textContent='Un ganador nominal puede cambiar al perturbar IV o plazo. La banda prueba IV bid–ask y salida a 1–2 semispreads. No cubre todos los errores del feed ni del modelo.';
    $('#observadas-resultados').hidden=false;
  }
  async function run(event){event?.preventDefault();if(!form.reportValidity())return;invalidate();$('#error').hidden=true;request=new AbortController();const signal=request.signal;$('#status').textContent='Evaluando la captura…';
    try{const res=await fetch('/api/observadas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({configuracion:cfg()}),signal});const r=await res.json();if(!res.ok)throw Error(r.error);if(signal.aborted)return;data=r;render(r);$('#status').textContent='Captura evaluada. Resultados históricos y condicionales.';}
    catch(e){if(e.name!=='AbortError'){$('#error').textContent=e.message;$('#error').hidden=false;$('#status').textContent='Sin resultados.';}}
  }
  form.addEventListener('submit',run);$('#observadas-ab').addEventListener('submit',compareAB);
  for(const side of ['a','b']){$('#observada-'+side).addEventListener('change',()=>{quantities(side);invalidateAB();});$('#n-'+side).addEventListener('input',invalidateAB);}
  $('#observada-posicion').addEventListener('change',selectMap);$('#observada-iv').addEventListener('change',selectMap);
  $('#observadas-export').addEventListener('click',()=>{if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify({analisis:data,comparacion_ab:ab},null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download='quantileflow-observadas-privado.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  run();
})();
