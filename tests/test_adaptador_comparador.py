"""Datos sintéticos: causalidad, separación de strikes y límites del adaptador."""
import numpy as np
import pandas as pd
import pytest

from quantileflow.adaptador_comparador import preparar_comparador
from quantileflow import contrato
from quantileflow.calendario import instante, instante_liquidacion, plazo_anios
from quantileflow.distribucion_pde import resolver_distribucion
from quantileflow.escenarios import ContratoEscenario, Escenario, comparar_contratos
from quantileflow.opciones import precio_bs


@pytest.fixture
def tablas():
    corte = instante("2026-10-09", "09:45")
    venc = pd.Timestamp("2026-11-09").date()
    t = plazo_anios(corte, instante_liquidacion(venc, "PM"))
    comunes = dict(sello_evento_utc=corte-pd.Timedelta(seconds=1), sello_snapshot_utc=corte,
                   disponible_utc=corte, recibido_utc=corte, proveedor="alpaca", feed="opra",
                   captura="2026-10-09T0945")
    filas = []
    for k in np.arange(95, 105.01, .25):
        for call in (True, False):
            precio = float(precio_bs(100, k, t, .04, .013, .2, call))
            filas.append(dict(**comunes, id_contrato=contrato.simbolo_occ("SPXW", venc, "C" if call else "P", k),
                raiz="SPXW", subyacente="SPX", strike=k, tipo="C" if call else "P", ejercicio="europeo",
                liquidacion="PM", vencimiento=venc, multiplicador=100, bid=max(.001, precio-.02),
                ask=precio+.02, tam_bid=10, tam_ask=10))
    refs = pd.DataFrame([dict(**comunes, subyacente="SPX", precio=100., bid=np.nan, ask=np.nan,
                             tipo_precio="observado")])
    return pd.DataFrame(filas), refs


def preparar(q, s, **kw):
    return preparar_comparador(q, s, "2026-10-09", "09:45", **kw)


def test_recupera_iv_plana_y_separa_entrenamiento_de_holdout(tablas):
    q, s = tablas
    r = preparar(q, s)
    assert r.apto_puntual and len(r.candidatos) == 6
    fit = next(iter(r.calibraciones.values()))
    assert fit["mid"] == pytest.approx(.2, abs=1e-8)
    assert fit["bid"] < fit["mid"] < fit["ask"]
    e = r.evaluacion
    assert not e.loc[e.entrenamiento, "strike"].isin(e.loc[e.holdout, "strike"]).any()
    assert e.groupby("strike").holdout.nunique().max() == 1  # separar call y put juntos


def test_holdout_no_influye_en_sigma_ajustada(tablas):
    q, s = tablas
    a = preparar(q, s)
    ids = a.evaluacion.loc[a.evaluacion.holdout, "id_contrato"]
    b = q.copy()
    b.loc[b.id_contrato.isin(ids), ["bid", "ask"]] += .005
    assert preparar(b, s).calibraciones == a.calibraciones


def test_indicativo_implicito_y_desfase_no_se_aceptan_por_modo_descriptivo(tablas):
    q, s = tablas
    q = q.assign(feed="indicative")
    s = s.assign(tipo_precio="implicito", sello_evento_utc=s.sello_evento_utc-pd.Timedelta(seconds=5))
    a, b = preparar(q, s), preparar(q, s, modo_descriptivo=True)
    assert not a.apto_puntual and not a.candidatos
    assert not b.apto_puntual and len(b.candidatos) == 6
    assert a.bloqueos == b.bloqueos and len(b.bloqueos) == 3


@pytest.mark.parametrize("col", ["sello_evento_utc", "sello_snapshot_utc", "disponible_utc", "recibido_utc"])
def test_sellos_posteriores_no_entran_ni_en_descriptivo(tablas, col):
    q, s = tablas
    q = q.copy()
    q.loc[0, col] += pd.Timedelta(seconds=2)
    with pytest.raises(ValueError, match="sello"):
        preparar(q, s, modo_descriptivo=True)


def test_feed_mezclado_y_americano_rechazados(tablas):
    q, s = tablas
    with pytest.raises(ValueError, match="mezclado"):
        preparar(q.assign(feed=np.where(q.tipo == "C", "opra", "indicative")), s)
    with pytest.raises(ValueError, match="europeo"):
        preparar(q.assign(ejercicio="americano"), s)


def test_calendario_y_multiplicador_no_se_inventan(tablas):
    q, s = tablas
    r = preparar(q, s)
    # El cambio de horario de noviembre agrega una hora al plazo ACT/365 en UTC.
    assert all(c.dte == pytest.approx(31+7.25/24) for c in r.candidatos)
    assert all(c.multiplicador == 100 for c in r.candidatos)
    with pytest.raises(ValueError, match="multiplicador"):
        preparar(q.assign(multiplicador=100.5), s)


def test_contrato_duplicado_y_referencia_duplicada_rechazados(tablas):
    q, s = tablas
    with pytest.raises(ValueError):
        preparar(pd.concat([q, q.iloc[[0]]]), s)
    with pytest.raises(ValueError, match="referencia"):
        preparar(q, pd.concat([s, s]))


def test_cambio_filas_e_indices_no_cambia_calibracion_o_candidatos(tablas):
    q, s = tablas
    a = preparar(q, s)
    b = q.sample(frac=1, random_state=11)
    b.index = [0]*len(b)
    c = preparar(b, s)
    assert a.calibraciones == c.calibraciones
    assert a.candidatos == c.candidatos


def test_insuficiencia_de_atm_no_inventa_sigma(tablas):
    q, s = tablas
    r = preparar(q, s, minimo_entrenamiento=10000)
    assert not r.apto_puntual and not r.candidatos and not r.calibraciones


def test_foto_posterior_no_cambia_calibracion_anterior(tablas):
    q, s = tablas
    a = preparar(q, s)
    futura = q.copy().assign(captura="2026-10-09T1000", bid=q.bid*2, ask=q.ask*2)
    assert preparar(pd.concat([q, futura]), s).calibraciones == a.calibraciones


def test_cotizacion_vieja_no_entra_en_candidatos(tablas):
    q, s = tablas
    elegido = preparar(q, s).candidatos[0].identificador
    b = q.copy()
    b.loc[b.id_contrato == elegido, "sello_evento_utc"] -= pd.Timedelta(seconds=61)
    r = preparar(b, s)
    assert elegido not in {c.identificador for c in r.candidatos}
    assert r.calidad["motivos"]["desfasada"] == 1


@pytest.mark.parametrize("call", [True, False])
def test_precio_sin_adjunto_coincide_con_valor_y_contabilidad_original(call):
    d = resolver_distribucion(100, 30/365, .04, .013, .25, nodos=301, pasos=200)
    assert d.precio_europeo(102.13, call) == d.valor_europeo(102.13, call).precio
    c = ContratoEscenario("sintetico", 102.13, 30, call, "europeo", .25, 2, 2.2)
    es = [Escenario("objetivo", 7, .03, -.02)]
    kw = dict(motor="pde", nodos=301, pasos=200, tasa=.04, q=.013)
    a = comparar_contratos([c], 100, es, 500, **kw)
    b = comparar_contratos([c], 100, es, 500, diagnosticos_pde=False, **kw)
    assert a["contratos"][0]["escenarios"]["objetivo"]["pnl"] == b["contratos"][0]["escenarios"]["objetivo"]["pnl"]


def test_cantidad_no_supera_limite_de_tamano_y_se_reserva_cierre():
    c = ContratoEscenario("ejemplo", 100, 30, True, "europeo", .25, 2, 2.2)
    es = [Escenario("vence", 30, 0)]
    r = comparar_contratos([c], 100, es, 10000, limites_cantidad={"ejemplo": 2})
    assert r["contratos"][0]["contratos"] == 2
    assert r["contratos"][0]["perdida_maxima_costos_asumidos"] == pytest.approx(442.6)
    assert not comparar_contratos([c], 100, es, 10000, limites_cantidad={"ejemplo": 0})["contratos"]
    with pytest.raises(ValueError, match="cantidad"):
        comparar_contratos([c], 100, es, 10000, limites_cantidad={"otro": 2})
