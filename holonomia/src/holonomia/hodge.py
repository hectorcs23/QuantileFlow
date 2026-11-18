"""Descomposición de Hodge de una cocadena 1 en el complejo de cliques.

El espacio de aristas se parte en tres pedazos ortogonales

    C¹ = im(d0)  ⊕  ker(d1) ∩ ker(d0ᵀ)  ⊕  im(d1ᵀ)
         gradiente        armónico          rotacional

con el significado económico de §0 del proyecto:

* **gradiente** — gauge puro. Existe un φ (los log-precios en un numerario
  común) que lo genera. No hay nada que explotar: toda holonomía es cero.
* **rotacional** — inconsistencia local, la que cierran los triángulos
  operables. Es el arbitraje triangular de toda la vida.
* **armónico** — inconsistencia global: ciclos que ninguna cara rellena.
  Es el análogo de c₁ del paper. Su dimensión es ``Grafo.betti1()``; si las
  caras rellenan todo el espacio de ciclos **vale cero por construcción**, y
  entonces medirlo no dice nada del mercado, sólo del complejo elegido.

La ortogonalidad es exacta porque ``d1 ∘ d0 = 0``: para cualesquiera φ y ψ,
``⟨d0 φ, d1ᵀ ψ⟩ = ⟨d1 d0 φ, ψ⟩ = 0``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .grafo import Grafo

UMBRAL_DENSO = 4000  # por debajo de esto se resuelve denso, que es exacto y rápido


@dataclass(frozen=True)
class Descomposicion:
    """Las tres partes de A y el potencial que genera el gradiente."""

    gradiente: np.ndarray
    rotacional: np.ndarray
    armonico: np.ndarray
    potencial: np.ndarray  # φ̂, con media cero en cada componente conexa

    @property
    def total(self) -> np.ndarray:
        return self.gradiente + self.rotacional + self.armonico

    def normas(self) -> dict[str, float]:
        """Normas L2 de cada parte y del total."""
        return {
            "gradiente": float(np.linalg.norm(self.gradiente)),
            "rotacional": float(np.linalg.norm(self.rotacional)),
            "armonico": float(np.linalg.norm(self.armonico)),
            "total": float(np.linalg.norm(self.total)),
        }

    def fracciones(self) -> dict[str, float]:
        """Reparto de la energía ``‖A‖²`` entre las tres partes.

        Como las partes son ortogonales, las tres fracciones suman 1 (salvo
        que A sea cero, y entonces salen ceros).

        **Ojo al usarla con precios.** El gradiente son los log-precios, que
        son números de orden 10, y la curvatura es de orden 1e-4. La fracción
        del gradiente sale 1 − 1e-10 siempre, diga lo que diga el mercado: no
        es un resultado, es la escala. Para comparar curvatura con curvatura
        está ``fracciones_de_curvatura``; para reportar tamaños, las normas en
        puntos base.
        """
        n = self.normas()
        total2 = n["total"] ** 2
        if total2 == 0.0:
            return {"gradiente": 0.0, "rotacional": 0.0, "armonico": 0.0}
        return {k: n[k] ** 2 / total2 for k in ("gradiente", "rotacional", "armonico")}

    def norma_curvatura(self) -> float:
        """``‖rotacional + armónico‖₂``: todo lo que no es gauge puro."""
        n = self.normas()
        return float(np.hypot(n["rotacional"], n["armonico"]))

    def fracciones_de_curvatura(self, tol_relativa: float = 1e-12) -> dict[str, float]:
        """Reparto **dentro de la curvatura**: local contra global.

        Es la pregunta de §2.5 («¿la inconsistencia es local o global?») sin
        el gradiente aplastándolo todo. Las dos fracciones suman 1.

        Cuando no hay curvatura, el cociente sería entre dos números del
        tamaño del épsilon de máquina y daría un reparto inventado. Por eso,
        si ``‖curvatura‖`` no llega a ``tol_relativa · ‖A‖``, se devuelven
        ceros: no hay nada que repartir.
        """
        n = self.normas()
        curv = np.hypot(n["rotacional"], n["armonico"])
        if curv <= tol_relativa * max(n["total"], 1.0):
            return {"rotacional": 0.0, "armonico": 0.0}
        return {"rotacional": (n["rotacional"] / curv) ** 2,
                "armonico": (n["armonico"] / curv) ** 2}


def _minimos_cuadrados(M: sp.spmatrix, b: np.ndarray) -> np.ndarray:
    """``argmin ‖M x − b‖₂`` de norma mínima, denso si el problema es chico."""
    if max(M.shape) <= UMBRAL_DENSO:
        x, *_ = np.linalg.lstsq(M.toarray(), b, rcond=None)
        return x
    return spla.lsqr(M, b, atol=1e-14, btol=1e-14, iter_lim=10 * max(M.shape))[0]


def _centrar_por_componente(g: Grafo, phi: np.ndarray) -> np.ndarray:
    """Fija el gauge: media cero de φ en cada componente conexa.

    El potencial sólo está determinado salvo una constante por componente
    (eso *es* la libertad de gauge), así que hay que elegir una para poder
    comparar corridas. No cambia el gradiente.
    """
    vecinos: dict[str, set[str]] = {m: set() for m in g.monedas}
    for a, b in g.aristas:
        vecinos[a].add(b)
        vecinos[b].add(a)
    idx = g.indice_moneda
    phi = phi.copy()
    vistas: set[str] = set()
    for raiz in g.monedas:
        if raiz in vistas:
            continue
        comp, pila = [], [raiz]
        while pila:
            x = pila.pop()
            if x in vistas:
                continue
            vistas.add(x)
            comp.append(x)
            pila.extend(y for y in vecinos[x] if y not in vistas)
        pos = [idx[m] for m in comp]
        phi[pos] -= phi[pos].mean()
    return phi


def descomponer(g: Grafo, A: np.ndarray) -> Descomposicion:
    """Parte ``A`` en gradiente, rotacional y armónico.

    ``A`` es un vector alineado con ``g.aristas`` (orientación canónica).
    Sin NaN: los instantes incompletos se filtran antes, en ``limpieza``.
    """
    A = np.asarray(A, dtype=float)
    if A.shape != (g.n_aristas,):
        raise ValueError(f"A debe tener forma ({g.n_aristas},), no {A.shape}")
    if not np.all(np.isfinite(A)):
        raise ValueError("A tiene valores no finitos; filtrar antes de descomponer")

    d0 = g.d0()
    phi = _centrar_por_componente(g, _minimos_cuadrados(d0, A))
    gradiente = d0 @ phi

    if g.n_caras:
        d1t = g.d1().T.tocsr()
        psi = _minimos_cuadrados(d1t, A)
        rotacional = d1t @ psi
    else:
        rotacional = np.zeros_like(A)

    armonico = A - gradiente - rotacional
    return Descomposicion(gradiente=gradiente, rotacional=rotacional,
                          armonico=armonico, potencial=phi)


def residuos_ortogonalidad(d: Descomposicion) -> dict[str, float]:
    """Productos internos entre partes y error de reconstrucción.

    Todo debería salir del orden del épsilon de máquina por la escala de A.
    Es el control de §2.6 escrito como función, para poder llamarlo también
    sobre datos reales y no sólo en los tests.
    """
    g_, r_, h_ = d.gradiente, d.rotacional, d.armonico
    return {
        "gradiente·rotacional": float(abs(g_ @ r_)),
        "gradiente·armonico": float(abs(g_ @ h_)),
        "rotacional·armonico": float(abs(r_ @ h_)),
    }


def error_reconstruccion(A: np.ndarray, d: Descomposicion) -> float:
    """``‖A − (gradiente + rotacional + armónico)‖₂``."""
    return float(np.linalg.norm(np.asarray(A, dtype=float) - d.total))


def precios_implicitos(g: Grafo, d: Descomposicion, numerario: str) -> dict[str, float]:
    """Precios que mejor explican A, expresados en ``numerario``.

    Devuelve ``precio[i]`` = unidades de ``numerario`` por unidad de ``i``.
    Es el gauge puro leído como economía: si el mercado fuera consistente,
    estos precios reproducirían todas las cotizaciones.
    """
    if numerario not in g.indice_moneda:
        raise KeyError(f"moneda desconocida: {numerario}")
    idx = g.indice_moneda
    # φ_i = −log(precio de i)  ⟹  precio_i / precio_num = exp(φ_num − φ_i)
    base = d.potencial[idx[numerario]]
    return {m: float(np.exp(base - d.potencial[idx[m]])) for m in g.monedas}
