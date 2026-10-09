"""Comprueba huellas privadas y emite exclusivamente conteos y estados agregados."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import pandas as pd
from quantileflow import alpaca


def paginas(objeto):
    if isinstance(objeto,dict):
        if "archivo" in objeto and "sha256" in objeto and "sha256_contenido" in objeto:
            yield objeto
        else:
            for valor in objeto.values():
                yield from paginas(valor)
    elif isinstance(objeto,list):
        for valor in objeto:
            yield from paginas(valor)


def auditar(datos, fecha, snapshot):
    datos = Path(datos).resolve()
    vistos = set()
    conteos = {}
    filas = []
    dimension = {}
    for carpeta in ("capturas","historico","eventos"):
        ms = alpaca.leer_manifiestos(datos, carpeta=carpeta)
        conteos[carpeta] = len(ms)
        for m in ms:
            for pagina in paginas(m):
                ruta = (datos/pagina["archivo"]).resolve()
                if not ruta.is_relative_to(datos):
                    raise ValueError("referencia fuera del directorio privado")
                clave = (pagina["archivo"],pagina["sha256"],pagina["sha256_contenido"])
                if clave not in vistos:
                    alpaca.leer_crudo(datos,pagina)  # archivo gzip, contenido descomprimido y JSON
                    vistos.add(clave)
            if m.get("fecha") == fecha:
                solicitudes = m.get("solicitudes",{})
                if carpeta == "capturas" and m.get("seleccion") and not dimension:
                    meta = alpaca.metadatos_contratos(alpaca.leer_crudo(datos,p)
                        for s in solicitudes.values() if s.get("tipo") == "contratos"
                        for p in s.get("paginas",[]))
                    for raiz, seleccion in m["seleccion"].items():
                        vs = {c["expiration_date"] for c in meta.values() if c["root_symbol"] == raiz}
                        elegidos, d = alpaca.elegir_vencimientos_multiples(vs,alpaca.LIQUIDACION[raiz],
                            pd.Timestamp(m["corte_utc"]),[7,14,30,60,90],2,raiz == "SPXW")
                        dimension[raiz] = {"expiraciones_en_metadata":len(vs),
                            "cadenas_actuales":len(seleccion["vencimientos"]),
                            "union_ampliada_solo_con_metadata_disponible":len(elegidos),
                            "objetivos_con_dos_lados": [t for t in (7,14,30,60,90)
                                if any(0<v<t for v in d.values()) and any(v>=t for v in d.values())]}
                filas.append({"tipo":carpeta,"hora":m.get("hora"),"estado":m.get("estado"),
                    "feed":m.get("feed_opciones",m.get("feed")),"codigo":m.get("codigo",{}).get("commit"),
                    "paginas":sum(len(s.get("paginas",[])) for s in solicitudes.values()),
                    "tardias":len(m.get("respuestas_despues_del_corte",[])),
                    "errores":len(m.get("errores",{})),
                    "duracion_s":(datetime.fromisoformat(m["fin_utc"])
                        -datetime.fromisoformat(m["inicio_utc"])).total_seconds()
                        if m.get("fin_utc") and m.get("inicio_utc") else None,
                    "sha256_manifiesto":hashlib.sha256((datos/m["_ruta"]).read_bytes()).hexdigest()})
    return {"snapshot_privado":snapshot,"fecha":fecha,"manifiestos":conteos,
            "paginas_unicas_verificadas":len(vistos),"integridad_huellas":"correcta", "dia":filas,
            "dimension_seleccion":dimension,
            "limite":"huellas verifican integridad del archivo; no veracidad de precios indicative"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--datos",type=Path,required=True)
    p.add_argument("--fecha",default="2026-10-09")
    p.add_argument("--snapshot",required=True)
    p.add_argument("--salida",type=Path,required=True)
    a = p.parse_args()
    informe = auditar(a.datos,a.fecha,a.snapshot)
    a.salida.parent.mkdir(parents=True,exist_ok=True)
    a.salida.write_text(json.dumps(informe,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(informe,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
