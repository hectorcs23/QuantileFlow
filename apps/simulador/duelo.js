"use strict";
window.dueloSimulador = (() => {
  const $=id=>document.getElementById(id);
  const usd=new Intl.NumberFormat("es-MX",{style:"currency",currency:"USD"});
  const signed=new Intl.NumberFormat("es-MX",{style:"currency",currency:"USD",signDisplay:"always"});
  const num=new Intl.NumberFormat("es-MX",{maximumFractionDigits:2});
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  let base=null, current=null, request=null, seq=0;
  function invalidar(text) {
    seq++;request?.abort();current=null;$("duelo-salida").hidden=true;
    $("duelo-aviso").textContent=text;
  }
  function limpiar() {invalidar("");base=null;$("duelo").hidden=true;}
  function limites(side) {
    const id=$("serie-"+side).value;
    const p=base.posiciones.find(p=>p.contrato===id);
    $("cantidad-"+side).max=String(p.cantidad);
    $("limite-"+side).textContent="Caben hasta "+p.cantidad+" · prima por contrato "+usd.format(p.prima_por_contrato);
  }
  function iniciar(data) {
    limpiar();if(!data.posiciones.length)return;
    base=data;$("duelo").hidden=false;
    const A=data.posiciones[0];
    const B=data.posiciones.filter(p=>p!==A).sort((a,b)=>b.prima_por_contrato-a.prima_por_contrato)[0]||A;
    for(const [side,p,n] of [["a",A,Math.min(3,A.cantidad)],["b",B,1]]){
      const sel=$("serie-"+side);sel.replaceChildren();
      for(const x of data.posiciones){
        const opt=node("option","K "+num.format(x.strike)+" · "+x.dte+" días");opt.value=x.contrato;sel.append(opt);
      }
      sel.value=p.contrato;$("cantidad-"+side).value=String(n);limites(side);
    }
    calcular();
  }
  function cabecera(id,cols){
    const tr=node("tr");cols.forEach(c=>tr.append(node("th",c)));
    $(id).tHead.replaceChildren(tr);$(id).tBodies[0].replaceChildren();
    return $(id).tBodies[0];
  }
  function representar(r) {
    const [a,b]=r.alternativas;
    const nombre=p=>p.lado+": "+p.cantidad+" × K "+num.format(p.strike)+" / "+p.dte+" d";
    const t=cabecera("duelo-capital",["",nombre(a),nombre(b)]);
    for(const [label,fmt] of [
      ["Prima / contrato",p=>usd.format(p.prima_por_contrato)],
      ["Capital reservado, con ambas comisiones",p=>usd.format(p.capital_reservado)],
      ["Efectivo libre",p=>usd.format(p.efectivo_libre)],
      ["Equilibrio al día "+base.configuracion.dias,p=>usd.format(p.equilibrio.spot)+" ("+num.format(p.equilibrio.movimiento_pct)+"%)"]
    ]){
      const tr=node("tr");tr.append(node("th",label),node("td",fmt(a)),node("td",fmt(b)));t.append(tr);
    }
    const table=cabecera("duelo-casos",["A la salida","Compra A","Compra B","Mayor capital final"]);
    const scale=Math.max(1,...r.escenarios.flatMap(s=>s.valores.map(v=>Math.abs(v.pnl??0))));
    for(const s of r.escenarios){
      const tr=node("tr"),th=node("th",s.nombre);
      th.append(node("small",num.format(s.movimiento_pct)+"% · día "+s.dias+" · IV "+num.format(s.iv_salida_pct)+"%"));tr.append(th);
      for(const v of s.valores){
        const td=node("td",v.pnl===null?"—":signed.format(v.pnl));
        if(v.pnl===null){td.append(node("small",v.motivo));}
        else{
          td.className=v.pnl<0?"neg":"pos";td.title="Capital final: "+usd.format(v.capital_final);
          const track=node("span"),bar=node("i");track.className="pnl-line";track.setAttribute("aria-hidden","true");
          const extent=50*Math.abs(v.pnl)/scale;bar.style.width=extent+"%";
          bar.style.left=(v.pnl<0?50-extent:50)+"%";bar.style.background=v.pnl<0?"var(--orange)":"var(--blue)";
          track.append(bar);td.append(track);
        }
        tr.append(td);
      }
      tr.append(node("td",s.mejores?s.mejores.join(" = "):"Sin comparar"));table.append(tr);
    }
    $("duelo-salida").hidden=false;
  }
  async function calcular(event) {
    event?.preventDefault();
    invalidar("");if(!base||!$("duelo-form").reportValidity())return;
    const ticket=seq;request=new AbortController();
    const cfg=base.configuracion;
    const alternativas=["a","b"].map(side=>({contrato:$("serie-"+side).value,cantidad:Number($("cantidad-"+side).value)}));
    $("duelo-aviso").textContent="Comparando ambas compras…";
    try{
      const resp=await fetch("/api/comparar-dos",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({configuracion:cfg,alternativas}),signal:request.signal});
      const data=await resp.json();if(ticket!==seq)return;
      if(!resp.ok)throw new Error(data.error||"No se pudo comparar");
      current={configuracion:cfg,...data};representar(data);
      $("duelo-aviso").textContent="Cantidad y prima de cada compra fijas en todos los escenarios.";
    }catch(e){if(ticket===seq && e.name!=="AbortError"){invalidar(e.message);}}
  }
  $("duelo-form").addEventListener("submit",calcular);
  for(const side of ["a","b"]){
    $("serie-"+side).addEventListener("change",()=>{limites(side);invalidar("Serie modificada. Revisa la cantidad y compara de nuevo.");});
    $("cantidad-"+side).addEventListener("input",()=>invalidar("Cantidad modificada. Compara de nuevo."));
  }
  $("duelo-export").addEventListener("click",()=>{
    if(!current)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)+"\n"],{type:"application/json"}));
    const a=node("a");a.href=url;a.download="quantileflow-comparacion-ab.json";document.body.append(a);
    a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  return {iniciar,limpiar};
})();
