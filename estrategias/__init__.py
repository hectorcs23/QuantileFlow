"""QuantileFlow · Estrategias: cuándo vender puts, cuándo comprarlos y cuándo no operar.

Subproyecto construido sobre el núcleo de ``quantileflow``. Toma la distribución
implícita ``Q`` reconstruida de la cadena de opciones, le añade una vista ``P``
declarada de forma explícita y compara con la misma vara todas las maneras de
expresar esa vista: vender puts, comprarlos, spreads, calls y la exposición
lineal.

El principio que lo ordena todo: **bajo ``Q`` ninguna estructura tiene ventaja
esperada**. Cualquier recomendación procede, exactamente, del desacuerdo entre
``P`` y ``Q``, y la ventaja de vender un put de strike ``K`` es

    D * int_0^K ( F_Q(s) - F_P(s) ) ds.

Creer que algo sube no basta: hay que creer que la caída concreta que el mercado
cotiza bajo ese strike está sobrevalorada. Si no se puede sostener esa
afirmación, el módulo se abstiene.

Versión de investigación. No hay datos de mercado ni resultados empíricos, y
nada de lo que produce es una recomendación de inversión.
"""
from . import (distribucion, estructuras, evaluacion, precios, recomendacion, robustez, sintetico,
               vista)

__version__ = "0.1.0"
__all__ = ["distribucion", "estructuras", "evaluacion", "precios", "recomendacion", "robustez",
           "sintetico", "vista"]
