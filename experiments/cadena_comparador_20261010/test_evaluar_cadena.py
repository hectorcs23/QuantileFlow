"""Integridad del crudo y modo causal de la prueba, sin proveedores ni datos reales."""
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("evaluar_cadena", Path(__file__).with_name("evaluar_cadena.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


@pytest.fixture
def entrada(tmp_path):
    tablas, crudo = tmp_path/"tablas", tmp_path/"crudo"
    tablas.mkdir()
    crudo.mkdir()
    for nombre in ("cotizaciones", "subyacente"):
        (tablas/f"{nombre}.parquet").write_bytes(b"tabla sintetica")
    cuerpo = b'{"resultado":"sintetico"}'
    pg = crudo/"pagina.json.gz"
    pg.write_bytes(gzip.compress(cuerpo))
    meta = {"archivo": pg.name, "sha256": mod.sha(pg),
            "sha256_contenido": mod.hashlib.sha256(cuerpo).hexdigest()}
    cap = crudo/"captura.json"
    cap.write_text(json.dumps({"solicitudes": {"cadena": {"paginas": [meta]}}}), encoding="utf-8")
    m = {"salidas": {n:mod.sha(tablas/f"{n}.parquet") for n in ("cotizaciones", "subyacente")},
         "capturas": [{"manifiesto": cap.name, "sha256": mod.sha(cap)}], "historico": [], "eventos": []}
    (tablas/"manifiesto_normalizacion.json").write_text(json.dumps(m), encoding="utf-8")
    return tablas, crudo


def test_formato_real_solicitudes_dict_y_tres_capas_de_huellas(entrada):
    tablas, crudo = entrada
    r = mod.integridad(tablas, crudo)
    assert r["manifiestos"] == r["paginas_unicas"] == 1
    assert r["estado"] == "huellas correctas"


@pytest.mark.parametrize("archivo", ["cotizaciones.parquet", "captura.json", "pagina.json.gz"])
def test_alteracion_detectada_en_tabla_manifiesto_o_pagina(entrada, archivo):
    tablas, crudo = entrada
    p = (tablas if archivo.endswith("parquet") else crudo)/archivo
    p.write_bytes(p.read_bytes()+b"alteracion")
    with pytest.raises(ValueError, match="huella"):
        mod.integridad(tablas, crudo)


def test_huella_cuerpo_se_verifica_aunque_gzip_y_manifiesto_tengan_hash_correcto(entrada):
    tablas, crudo = entrada
    cap = crudo/"captura.json"
    d = json.loads(cap.read_text(encoding="utf-8"))
    d["solicitudes"]["cadena"]["paginas"][0]["sha256_contenido"] = "0"*64
    cap.write_text(json.dumps(d), encoding="utf-8")
    m = json.loads((tablas/"manifiesto_normalizacion.json").read_text(encoding="utf-8"))
    m["capturas"][0]["sha256"] = mod.sha(cap)
    (tablas/"manifiesto_normalizacion.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError, match="contenido"):
        mod.integridad(tablas, crudo)
