"""Restricciones necesarias de precios europeos, sin sonrisa ni densidad elegidas.

Una solución factible en los strikes finitos no certifica una extensión global
ni condiciones de calendario. Una infactibilidad sí descarta cualquier modelo
que cumpla estas restricciones, bajo el descuento y forward declarados.
"""
import numpy as np
from scipy.optimize import linprog
from scipy import sparse


def diagnosticar(filas, forward, descuento, *, forward_libre=False,
                descuento_libre=False, nivel="convexidad", objetivo="maximo"):
    """Mínima ampliación bid/ask, medida en spreads completos originales.

    Cada banda pasa de [bid, ask] a [bid-rho_i*spread, ask+rho_i*spread].
    maximo minimiza un rho común; media minimiza el promedio de rho_i >= 0.
    El segundo no minimiza el número de cotizaciones modificadas.
    Forward libre se ajusta a posteriori: nunca es una predicción reservada.
    Descuento libre permite D >= 0 sin límite superior, junto con D*F libre.
    Es una relajación matemática extrema, no una tasa estimada económicamente.
    """
    if nivel not in ("paridad_cotas", "verticales", "convexidad"):
        raise ValueError("nivel desconocido")
    if objetivo not in ("maximo", "media"):
        raise ValueError("objetivo desconocido")
    if descuento_libre and not forward_libre:
        raise ValueError("el control con descuento libre requiere forward libre")
    if not np.isfinite([forward, descuento]).all() or min(forward, descuento) <= 0:
        raise ValueError("forward y descuento positivos requeridos")
    if len(filas) == 0 or filas.duplicated(["strike", "tipo"]).any():
        raise ValueError("datos vacíos o lado duplicado por strike")
    K, bid, ask = [filas[c].to_numpy(float) for c in ("strike", "bid", "ask")]
    if (not np.isfinite(np.r_[K, bid, ask]).all() or np.any(K <= 0)
            or np.any(bid < 0) or np.any(ask <= bid) or not filas.tipo.isin(["C", "P"]).all()):
        raise ValueError("bandas o tipos inválidos")
    strikes = np.unique(K)
    x = np.r_[0., strikes / forward]
    n, nc = len(K), len(x)
    m = nc + int(descuento_libre)
    indices = np.searchsorted(strikes, K) + 1
    # z[0]=F/F_ref; z[j]=C(K_j)/(D*F_ref). C(0)=D*F.
    A = np.zeros((n, m))
    A[np.arange(n), indices] = 1.
    puts = filas.tipo.eq("P").to_numpy()
    A[puts, 0] = -1.
    offset = np.where(puts, K / forward, 0.)
    if descuento_libre:
        A[puts, nc] = K[puts] / forward
        offset = np.zeros(n)
    escala = descuento * forward
    lo, hi, ancho = bid / escala, ask / escala, (ask - bid) / escala
    restricciones, rhs = [], []
    # Calls no negativas por bounds. Calls <= D F y puts >= 0.
    for j in range(1, nc):
        row = np.zeros(m); row[j] = 1; row[0] = -1
        put_positivo = -row.copy()
        if descuento_libre:
            put_positivo[nc] = -x[j]
        restricciones.extend([row, put_positivo])
        rhs.extend([0., 0. if descuento_libre else x[j]])
    if nivel in ("verticales", "convexidad"):
        for j, dx in enumerate(np.diff(x)):
            row = np.zeros(m); row[j + 1] = 1; row[j] = -1
            limite_vertical = -row.copy()
            if descuento_libre:
                limite_vertical[nc] = -dx
            restricciones.extend([row, limite_vertical])
            rhs.extend([0., 0. if descuento_libre else dx])
    if nivel == "convexidad":
        for j in range(nc - 2):
            d1, d2 = x[j + 1] - x[j], x[j + 2] - x[j + 1]
            row = np.zeros(m)
            row[j] = -1 / d1
            row[j + 1] = 1 / d1 + 1 / d2
            row[j + 2] = -1 / d2
            restricciones.append(row); rhs.append(0.)
    R = sparse.csr_matrix(np.asarray(restricciones))
    ne = 1 if objetivo == "maximo" else n
    E = sparse.csr_matrix(ancho[:, None]) if ne == 1 else sparse.diags(ancho)
    G = sparse.vstack([
        sparse.hstack([R, sparse.csr_matrix((len(rhs), ne))]),
        sparse.hstack([sparse.csr_matrix(A), -E]),
        sparse.hstack([sparse.csr_matrix(-A), -E]),
    ], format="csr")
    h = np.r_[rhs, hi - offset, -lo + offset]
    costo = np.r_[np.zeros(m), np.full(ne, 1 / ne)]
    bounds = [(0., None)] * (m + ne)
    bounds[0] = (0., None) if forward_libre else (1., 1.)
    sol = linprog(costo, A_ub=G, b_ub=h, bounds=bounds, method="highs",
                  options={"primal_feasibility_tolerance": 1e-9,
                           "dual_feasibility_tolerance": 1e-9, "time_limit": 30.})
    if not sol.success:
        raise RuntimeError(f"LP sin óptimo certificado: {sol.message}")
    residuos = G @ sol.x - h
    violacion = max(0., float(residuos.max()), float(-sol.x.min()),
                   abs(sol.x[0] - 1) if not forward_libre else 0.)
    dual = float(h @ sol.ineqlin.marginals)
    for j, (a, b) in enumerate(bounds):
        dual += a * sol.lower.marginals[j]
        if b is not None:
            dual += b * sol.upper.marginals[j]
    brecha = abs(float(sol.fun) - dual)
    estacionariedad = costo - np.asarray(G.T @ sol.ineqlin.marginals).ravel()
    estacionariedad -= sol.lower.marginals + sol.upper.marginals
    violacion_dual = max(float(abs(estacionariedad).max()), 0.,
                         float(sol.ineqlin.marginals.max()),
                         float((-sol.lower.marginals).max()),
                         float(sol.upper.marginals.max()))
    if violacion > 1e-8 or violacion_dual > 1e-7 or brecha > 1e-6 * max(1., abs(sol.fun)):
        raise RuntimeError(f"LP no supera verificación independiente: {violacion=}, {brecha=}")
    precios = (A @ sol.x[:m] + offset) * escala
    fuera = np.maximum(np.maximum(bid - precios, precios - ask), 0.)
    distancias = fuera / (ask - bid)
    return dict(
        nivel=nivel, objetivo=objetivo, forward_libre=bool(forward_libre),
        descuento_libre=bool(descuento_libre), filas=n,
        relajacion=float(sol.fun), factible_sin_relajar=bool(sol.fun <= 1e-6),
        max_distancia_spreads=float(distancias.max()), media_distancia_spreads=float(distancias.mean()),
        media_distancia_precio=float(fuera.mean()), violacion_primal=violacion,
        brecha_primal_dual=brecha, violacion_dual=violacion_dual, iteraciones=int(sol.nit),
        forward_ratio_diagnostico=(float(sol.x[0] / sol.x[nc]) if sol.x[nc] > 0 else None)
            if descuento_libre else float(sol.x[0]),
        descuento_ratio_diagnostico=float(sol.x[nc]) if descuento_libre else 1.,
        precios=precios,
        relajaciones_por_fila=distancias)
