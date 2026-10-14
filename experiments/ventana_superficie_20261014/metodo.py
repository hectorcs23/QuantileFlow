"""Split anidado por strike, conservando las reservas históricas."""
import numpy as np


def dividir_anidado(amplia, original):
    key = ['vencimiento', 'strike']
    if amplia.id_contrato.duplicated().any() or original.id_contrato.duplicated().any():
        raise ValueError('contrato duplicado')
    if not set(original.id_contrato).issubset(amplia.id_contrato):
        raise ValueError('faltan filas originales')
    flags = original.groupby(key).holdout
    if (flags.nunique() != 1).any():
        raise ValueError('call y put históricos en grupos distintos')
    known = flags.first().to_dict()
    out = amplia.copy(deep=True)
    assignment = dict(known)
    for maturity, group in out.groupby('vencimiento', sort=True):
        extra = sorted(k for k in group.strike.unique() if (maturity, k) not in known)
        assignment.update({(maturity, k): j % 3 == 0 for j, k in enumerate(extra)})
    out['holdout'] = [assignment[(v, k)] for v, k in zip(out.vencimiento, out.strike)]
    out['entrenamiento'] = ~out.holdout
    out['historico'] = out.id_contrato.isin(original.id_contrato)
    return out


def seleccionar(filas, ancho):
    if not np.isfinite(ancho) or ancho <= 0:
        raise ValueError('ancho positivo requerido')
    return filas[filas.k.abs() <= ancho].copy()
