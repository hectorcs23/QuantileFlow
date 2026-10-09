import importlib.util
from pathlib import Path
import tomllib

import pytest

RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("captura_manual", RAIZ / "experiments/pde_gratis_20261009/captura_manual.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def config():
    return tomllib.loads(mod.CONFIG.read_text(encoding="utf-8"))


def test_destino_aislado_y_alamacen_existente(tmp_path):
    assert mod.validar(config(), tmp_path / "nuevo") == (tmp_path / "nuevo").resolve()
    with pytest.raises(ValueError, match="nuevo"):
        mod.validar(config(), tmp_path)
    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="Git"):
        mod.validar(config(), tmp_path / "nuevo")


@pytest.mark.parametrize("campo,valor", [("feed_opciones", "opra"), ("feed_acciones", "sip"),
                                          ("hilos", 13), ("plazo_s", 61)])
def test_rechaza_feeds_pagados_y_limites(campo, valor):
    c = config()
    c["captura"][campo] = valor
    with pytest.raises(ValueError):
        mod.validar(c, None)


def test_plan_no_ejecuta_api_y_sin_claves_no_arranca(monkeypatch):
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: pytest.fail("no debe arrancar captura"))
    monkeypatch.setattr(mod.sys, "argv", ["captura_manual"])
    assert mod.main() == 0
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    monkeypatch.setattr(mod.sys, "argv", ["captura_manual", "--ejecutar", "--datos", "nuevo_privado"])
    assert mod.main() == 2
