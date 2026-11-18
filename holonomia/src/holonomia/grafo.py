"""Grafo de monedas, complejo de cliques y operadores de borde.

Convención de gauge
-------------------
Se fija aquí y la usa todo el paquete. Sea

    φ_i = −log(precio de una unidad de la moneda i en un numerario común),

es decir, el log de cuántas unidades de ``i`` compra una unidad del numerario.
Con esa elección, para la arista dirigida ``i → j``

    A_ij = φ_j − φ_i = log(unidades de j que se obtienen por unidad de i),

que es a la vez «el gradiente de φ» y «el log del tipo de conversión». Las dos
lecturas del proyecto coinciden sin signo espurio. Un cambio de numerario
desplaza φ en una constante y deja A igual; una reexpresión arbitraria
φ_i → φ_i + c_i es el cambio de gauge A_ij → A_ij + c_j − c_i.

La holonomía de un ciclo C es

    H(C) = Σ_{(i→j)∈C} A_ij = log(producto de los tipos de conversión),

invariante de gauge, y **H(C) > 0 significa que el ciclo devuelve más de lo que
entró**: arbitraje, si los precios son ejecutables.

Un símbolo de Alpaca ``BASE/COTIZADA`` con precio ``m`` cotiza «m unidades de
COTIZADA por unidad de BASE», así que la arista dirigida ``BASE → COTIZADA``
lleva ``A = log(m)`` y la contraria ``−log(m)`` en la versión con precio medio.

Orientación canónica
--------------------
Cada arista no dirigida ``{i, j}`` se almacena una sola vez, orientada de la
moneda alfabéticamente menor a la mayor. Un cocadena 1 es un vector de numpy
alineado con ``Grafo.aristas``; leerlo en la dirección contraria cambia el
signo. Las 2-celdas ``(i, j, k)`` con ``i < j < k`` se orientan como el ciclo
``i → j → k → i``, cuyo borde es ``e_ij + e_jk − e_ik``.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp


def _arista(a: str, b: str) -> tuple[str, str]:
    """Arista en orientación canónica (alfabética)."""
    return (a, b) if a < b else (b, a)


@dataclass(frozen=True)
class Grafo:
    """Complejo de cliques de 2 dimensiones sobre el grafo de monedas.

    ``monedas``  vértices, ordenados.
    ``aristas``  pares cotizados, en orientación canónica y ordenados.
    ``caras``    2-celdas (triángulos operables), ``i < j < k``. Pueden ser
                 menos que todos los triángulos del grafo: ahí está la
                 diferencia entre «hay parte armónica» y «no la hay».
    """

    monedas: tuple[str, ...]
    aristas: tuple[tuple[str, str], ...]
    caras: tuple[tuple[str, str, str], ...]

    def __post_init__(self) -> None:
        if len(set(self.aristas)) != len(self.aristas):
            raise ValueError("aristas repetidas")
        for a, b in self.aristas:
            if a >= b:
                raise ValueError(f"arista no canónica: {(a, b)}")
            if a not in self.indice_moneda or b not in self.indice_moneda:
                raise ValueError(f"arista con moneda desconocida: {(a, b)}")
        for cara in self.caras:
            if list(cara) != sorted(cara):
                raise ValueError(f"cara no canónica: {cara}")
            for par in itertools.combinations(cara, 2):
                if par not in self.indice_arista:
                    raise ValueError(f"la cara {cara} usa una arista inexistente: {par}")

    # -- índices ---------------------------------------------------------
    @property
    def indice_moneda(self) -> dict[str, int]:
        return {m: i for i, m in enumerate(self.monedas)}

    @property
    def indice_arista(self) -> dict[tuple[str, str], int]:
        return {e: i for i, e in enumerate(self.aristas)}

    @property
    def n_monedas(self) -> int:
        return len(self.monedas)

    @property
    def n_aristas(self) -> int:
        return len(self.aristas)

    @property
    def n_caras(self) -> int:
        return len(self.caras)

    # -- operadores ------------------------------------------------------
    def d0(self) -> sp.csr_matrix:
        """Gradiente ``C⁰ → C¹``: ``(d0 φ)(i→j) = φ_j − φ_i`` en cada arista canónica."""
        idx = self.indice_moneda
        filas, cols, datos = [], [], []
        for f, (a, b) in enumerate(self.aristas):
            filas += [f, f]
            cols += [idx[a], idx[b]]
            datos += [-1.0, 1.0]
        return sp.csr_matrix((datos, (filas, cols)), shape=(self.n_aristas, self.n_monedas))

    def d1(self) -> sp.csr_matrix:
        """Rotacional ``C¹ → C²``: ``(d1 A)(i,j,k) = A_ij + A_jk − A_ik``."""
        idx = self.indice_arista
        filas, cols, datos = [], [], []
        for f, (i, j, k) in enumerate(self.caras):
            for par, signo in (((i, j), 1.0), ((j, k), 1.0), ((i, k), -1.0)):
                filas.append(f)
                cols.append(idx[par])
                datos.append(signo)
        return sp.csr_matrix((datos, (filas, cols)), shape=(self.n_caras, self.n_aristas))

    # -- topología -------------------------------------------------------
    def n_componentes(self) -> int:
        """Componentes conexas, por búsqueda en anchura."""
        vecinos: dict[str, set[str]] = {m: set() for m in self.monedas}
        for a, b in self.aristas:
            vecinos[a].add(b)
            vecinos[b].add(a)
        vistas: set[str] = set()
        n = 0
        for raiz in self.monedas:
            if raiz in vistas:
                continue
            n += 1
            pila = [raiz]
            while pila:
                x = pila.pop()
                if x in vistas:
                    continue
                vistas.add(x)
                pila.extend(y for y in vecinos[x] if y not in vistas)
        return n

    def rango_ciclos(self) -> int:
        """Dimensión del espacio de ciclos del grafo: ``E − V + componentes``."""
        return self.n_aristas - self.n_monedas + self.n_componentes()

    def betti1(self) -> int:
        """``b₁`` del complejo: dimensión del espacio armónico.

        ``b₁ = dim ker(d1) − dim im(d0) = (E − rango d1) − (V − componentes)``.
        Vale cero cuando las caras rellenan todo el espacio de ciclos; en ese
        caso **no hay parte armónica posible** y toda la inconsistencia es
        rotacional, sea cual sea el precio.
        """
        if self.n_caras == 0:
            return self.rango_ciclos()
        rango_d1 = int(np.linalg.matrix_rank(self.d1().toarray()))
        return self.rango_ciclos() - rango_d1

    # -- cocadenas -------------------------------------------------------
    def cocadena(self, valores: dict[tuple[str, str], float]) -> np.ndarray:
        """Vector de ``C¹`` a partir de valores en aristas dirigidas.

        ``valores`` lleva pares ``(i, j) -> A_ij``. Si un par viene en la
        dirección contraria a la canónica se guarda con el signo cambiado; dar
        las dos direcciones de la misma arista con valores incompatibles es un
        error (eso sólo pasa con precios ejecutables, que no son una cocadena:
        para esos está ``holonomia.holonomia_ejecutable``).
        """
        A = np.full(self.n_aristas, np.nan)
        idx = self.indice_arista
        for (a, b), v in valores.items():
            e = _arista(a, b)
            if e not in idx:
                raise KeyError(f"arista inexistente: {(a, b)}")
            signo = 1.0 if (a, b) == e else -1.0
            nuevo = signo * v
            previo = A[idx[e]]
            if not np.isnan(previo) and not np.isclose(previo, nuevo):
                raise ValueError(f"valores incompatibles en la arista {e}")
            A[idx[e]] = nuevo
        return A

    def holonomia(self, A: np.ndarray, ciclo: list[str]) -> float:
        """``H(C) = Σ A_ij`` sobre el ciclo dado como lista de monedas.

        El ciclo se cierra solo: ``['BTC','USD','ETH']`` recorre
        ``BTC → USD → ETH → BTC``. Si viene cerrado explícitamente se acepta
        igual.
        """
        nodos = list(ciclo)
        if len(nodos) > 1 and nodos[0] == nodos[-1]:
            nodos = nodos[:-1]
        if len(nodos) < 2:
            raise ValueError("un ciclo necesita al menos dos monedas")
        idx = self.indice_arista
        total = 0.0
        for a, b in zip(nodos, nodos[1:] + nodos[:1]):
            e = _arista(a, b)
            if e not in idx:
                raise KeyError(f"el ciclo usa una arista inexistente: {(a, b)}")
            total += A[idx[e]] if (a, b) == e else -A[idx[e]]
        return float(total)


# -- construcción ---------------------------------------------------------
def triangulos(monedas, aristas) -> tuple[tuple[str, str, str], ...]:
    """Todos los triángulos (3-cliques) del grafo, en orden canónico."""
    conjunto = set(aristas)
    vecinos: dict[str, set[str]] = {m: set() for m in monedas}
    for a, b in conjunto:
        vecinos[a].add(b)
        vecinos[b].add(a)
    salida = []
    for i, j, k in itertools.combinations(sorted(monedas), 3):
        if j in vecinos[i] and k in vecinos[j] and k in vecinos[i]:
            salida.append((i, j, k))
    return tuple(salida)


def desde_aristas(pares, caras=None) -> Grafo:
    """Grafo a partir de pares de monedas ``(a, b)``.

    Con ``caras=None`` se toman **todos** los triángulos del grafo como
    2-celdas. Para medir parte armónica hay que pasar un subconjunto: los
    triángulos realmente operables.
    """
    aristas = sorted({_arista(a, b) for a, b in pares})
    monedas = tuple(sorted({m for e in aristas for m in e}))
    caras = triangulos(monedas, aristas) if caras is None else tuple(
        sorted(tuple(sorted(c)) for c in caras)
    )
    return Grafo(monedas=monedas, aristas=tuple(aristas), caras=caras)


def desde_simbolos(simbolos, caras=None) -> Grafo:
    """Grafo a partir de símbolos de Alpaca ``'BASE/COTIZADA'``."""
    pares = []
    for s in simbolos:
        if "/" not in s:
            raise ValueError(f"símbolo sin barra: {s!r}")
        base, cotizada = s.split("/")
        pares.append((base, cotizada))
    return desde_aristas(pares, caras=caras)


def ciclos_simples(g: Grafo, longitud_max: int = 3) -> list[list[str]]:
    """Ciclos simples del grafo hasta ``longitud_max`` monedas.

    Cada ciclo sale una vez, en la orientación que empieza por su moneda
    alfabéticamente menor y sigue hacia el menor de sus dos vecinos en el
    ciclo. Enumeración directa, sin pasar por la descomposición: sirve de
    contraste independiente (§2.6).
    """
    if longitud_max < 3:
        return []
    conjunto = set(g.aristas)
    vistos: set[tuple[str, ...]] = set()
    salida: list[list[str]] = []
    for k in range(3, longitud_max + 1):
        for combo in itertools.combinations(g.monedas, k):
            # permutaciones que fijan el primer elemento: cada ciclo y su inverso
            cabeza, resto = combo[0], combo[1:]
            for perm in itertools.permutations(resto):
                nodos = (cabeza,) + perm
                if perm[0] > perm[-1]:       # descarta la orientación inversa
                    continue
                if all(_arista(a, b) in conjunto
                       for a, b in zip(nodos, nodos[1:] + (nodos[0],))):
                    if nodos not in vistos:
                        vistos.add(nodos)
                        salida.append(list(nodos))
    return salida
