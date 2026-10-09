import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("auditar_crudo",RAIZ/"experiments/pde_gratis_20261009/auditar_crudo.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def muestra(tmp_path):
    contenido = b'{"snapshots":{}}'
    bruto = gzip.compress(contenido,mtime=0)
    raw = tmp_path/"raw/alpaca/prueba.json.gz"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(bruto)
    pagina = dict(archivo="raw/alpaca/prueba.json.gz",sha256=hashlib.sha256(bruto).hexdigest(),
                  sha256_contenido=hashlib.sha256(contenido).hexdigest())
    m = dict(fecha="2026-10-09",hora="09:45",estado="completa",
             solicitudes={"prueba":dict(paginas=[pagina])})
    manifiesto = tmp_path/"raw/alpaca/capturas/2026-10-09/corte.json"
    manifiesto.parent.mkdir(parents=True)
    manifiesto.write_text(json.dumps(m),encoding="utf-8")
    return raw, manifiesto, m


def test_huella_archivo_y_contenido_y_rechazo_corrupcion(tmp_path):
    raw, manifiesto, m = muestra(tmp_path)
    r = mod.auditar(tmp_path,"2026-10-09","snapshot-prueba")
    assert r["paginas_unicas_verificadas"] == 1
    raw.write_bytes(raw.read_bytes()+b"alterado")
    with pytest.raises(RuntimeError,match="hash del archivo"):
        mod.auditar(tmp_path,"2026-10-09","snapshot-prueba")
    raw.write_bytes(gzip.compress(b'{"snapshots":{"alterado":1}}',mtime=0))
    m["solicitudes"]["prueba"]["paginas"][0]["sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
    manifiesto.write_text(json.dumps(m),encoding="utf-8")
    with pytest.raises(RuntimeError,match="hash del contenido"):
        mod.auditar(tmp_path,"2026-10-09","snapshot-prueba")


def test_rechaza_referencia_fuera_del_almacen(tmp_path):
    _, manifiesto, m = muestra(tmp_path)
    m["solicitudes"]["prueba"]["paginas"][0]["archivo"] = "../fuera.json.gz"
    manifiesto.write_text(json.dumps(m),encoding="utf-8")
    with pytest.raises(ValueError,match="fuera"):
        mod.auditar(tmp_path,"2026-10-09","snapshot-prueba")
