"""Almacenamiento reproducible: crudo inmutable, Parquet determinista y huella del entorno."""
import json
import os
import stat

import numpy as np
import pandas as pd
import pytest

from quantileflow import almacen
from quantileflow import calendario as cal
from quantileflow import contrato as ct
from quantileflow import sintetico as sn


def test_crudo_inmutable_y_direccionado_por_contenido(tmp_path):
    origen = tmp_path / "cadena.csv"
    origen.write_text("strike,bid,ask\n100,1.0,1.1\n")
    info = almacen.guardar_crudo(origen, tmp_path / "raw")
    assert info["sha256"] == almacen.sha256_archivo(origen)
    assert info["ruta"].endswith(f"{info['sha256']}_cadena.csv")
    assert not os.stat(info["ruta"]).st_mode & stat.S_IWUSR  # solo lectura
    assert almacen.guardar_crudo(origen, tmp_path / "raw") == info  # idempotente
    # Un archivo distinto con el mismo nombre no pisa al anterior: tiene otro hash y otra ruta.
    origen.write_text("strike,bid,ask\n100,1.0,1.2\n")
    otro = almacen.guardar_crudo(origen, tmp_path / "raw")
    assert otro["ruta"] != info["ruta"] and os.path.exists(info["ruta"])


def test_crudo_alterado_se_detecta(tmp_path):
    origen = tmp_path / "a.csv"
    origen.write_text("x\n1\n")
    info = almacen.guardar_crudo(origen, tmp_path / "raw")
    os.chmod(info["ruta"], stat.S_IRUSR | stat.S_IWUSR)
    with open(info["ruta"], "a") as f:
        f.write("2\n")
    with pytest.raises(RuntimeError):
        almacen.guardar_crudo(origen, tmp_path / "raw")


def test_parquet_ida_y_vuelta_exacta_y_determinista(tmp_path):
    fechas = cal.sesiones("2025-11-17", "2025-11-18")
    cot, sub, _ = sn.mercado_sintetico(fechas, semilla=2, rango_k=(-0.03, 0.02), sesiones_extra=1)
    h1 = almacen.escribir_tabla(cot, tmp_path / "a.parquet")
    h2 = almacen.escribir_tabla(cot, tmp_path / "b.parquet")
    assert h1 == h2
    leida = almacen.leer_tabla(tmp_path / "a.parquet")
    assert ct.validar(leida) == []
    pd.testing.assert_frame_equal(leida.reset_index(drop=True), cot.reset_index(drop=True),
                                  check_dtype=False)
    assert str(leida["sello_snapshot_utc"].dt.tz) == "UTC"


def test_huellas(tmp_path):
    entorno = almacen.huella_entorno()
    assert set(entorno) == {"python", "plataforma", "paquetes", "git"}
    assert entorno["paquetes"]["numpy"] == np.__version__
    assert almacen.huella_datos({"b": 1, "a": [1, 2]}) == almacen.huella_datos({"a": [1, 2], "b": 1})
    h = almacen.escribir_json({"z": 1, "a": 2}, tmp_path / "m.json")
    assert (tmp_path / "m.json").read_text().index('"a"') < (tmp_path / "m.json").read_text().index('"z"')
    assert h == almacen.sha256_archivo(tmp_path / "m.json")


def test_escritura_atomica_que_no_sobrescribe(tmp_path):
    ruta = tmp_path / "manifiesto.json"
    h = almacen.escribir_json_nuevo({"estado": "completa"}, ruta)
    assert h == almacen.sha256_archivo(ruta) and not os.stat(ruta).st_mode & stat.S_IWUSR
    with pytest.raises(FileExistsError):
        almacen.escribir_json_nuevo({"estado": "parcial"}, ruta)
    assert json.loads(ruta.read_text()) == {"estado": "completa"}
    assert [p.name for p in tmp_path.iterdir()] == ["manifiesto.json"]  # sin temporales a la vista
