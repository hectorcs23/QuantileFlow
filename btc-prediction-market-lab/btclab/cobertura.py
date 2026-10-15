"""Auditoria de cobertura del almacen (Paso 2, entrega).

Responde, por dia y contrato: cuantas observaciones hay, que huecos, que latencia
de cada fuente, cuanta antiguedad arrastran las cotizaciones y cuanto se separan
el spot y el indice.

Es el documento que dice si los datos **alcanzan** para el analisis que se
declara. Un reporte de cobertura con huecos grandes o con antiguedad alta no es
un detalle de calidad: es la razon por la que una conclusion no puede afirmarse.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .almacen import Almacen, registro_a_observacion
from .libro import Lado, Libro
from .tiempo import desde_iso


@dataclass
class ResumenFlujo:
    """Estadisticos de un flujo de datos."""

    flujo: str
    n: int = 0
    corruptos: int = 0
    contratos: set[str] = field(default_factory=set)
    dias: set[str] = field(default_factory=set)
    latencias_s: list[float] = field(default_factory=list)
    separaciones_s: list[float] = field(default_factory=list)
    primera: str | None = None
    ultima: str | None = None

    def como_dict(self, intervalo_esperado_s: float | None = None) -> dict:
        def resumen(valores: list[float]) -> dict | None:
            if not valores:
                return None
            ordenados = sorted(valores)
            return {
                "n": len(ordenados),
                "min": round(ordenados[0], 3),
                "p50": round(statistics.median(ordenados), 3),
                "p95": round(ordenados[min(len(ordenados) - 1, int(0.95 * len(ordenados)))], 3),
                "max": round(ordenados[-1], 3),
            }

        datos = {
            "n": self.n,
            "corruptos": self.corruptos,
            "contratos": len(self.contratos),
            "dias": sorted(self.dias),
            "primera": self.primera,
            "ultima": self.ultima,
            "latencia_fuente_s": resumen(self.latencias_s),
            "separacion_entre_recepciones_s": resumen(self.separaciones_s),
        }
        if intervalo_esperado_s is not None and self.separaciones_s:
            huecos = [s for s in self.separaciones_s if s > intervalo_esperado_s]
            datos["huecos"] = {
                "intervalo_esperado_s": intervalo_esperado_s,
                "n": len(huecos),
                "peor_s": round(max(huecos), 3) if huecos else 0.0,
                "fraccion": round(len(huecos) / len(self.separaciones_s), 4),
            }
        return datos


def _precio_spot(fuente: str, payload: dict) -> Decimal | None:
    """Extrae el precio segun la forma de cada fuente.

    Coinbase entrega ``price`` directo; Kraken entrega OHLC y hay que tomar el
    cierre de la ultima vela. Tratar ambas igual perderia Kraken en silencio.
    """
    cuerpo = payload.get("cuerpo") or {}
    if not isinstance(cuerpo, dict):
        return None
    if "price" in cuerpo:
        return _a_decimal(cuerpo.get("price"))
    resultado = cuerpo.get("result")
    if isinstance(resultado, dict):
        for clave, series in resultado.items():
            if clave == "last" or not series:
                continue
            try:
                return _a_decimal(series[-1][4])  # cierre de la ultima vela
            except (IndexError, TypeError):
                continue
    return None


def _a_decimal(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        return None


def auditar(
    almacen: Almacen, intervalos_esperados_s: dict[str, float] | None = None
) -> dict:
    """Recorre el almacen y produce el reporte de cobertura."""
    intervalos = intervalos_esperados_s or {}
    resumenes: dict[str, ResumenFlujo] = {}
    ultima_recepcion: dict[tuple[str, str], str] = {}

    # Controles especificos
    pares_libro_mercado = {"comparados": 0, "discrepantes": 0, "detalles": []}
    estructura_libro = {"snapshots": 0, "cuadra": 0, "no_cuadra": 0}
    brecha_spot_indice: list[float] = []
    mercados_por_contrato: dict[str, list[dict]] = defaultdict(list)
    libros_por_contrato: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    spot_por_fuente: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    resultados: dict[str, dict] = {}

    for flujo in almacen.flujos():
        resumen = ResumenFlujo(flujo=flujo)
        resumenes[flujo] = resumen
        for registro in almacen.leer(flujo):
            if registro.get("_corrupto"):
                resumen.corruptos += 1
                continue
            resumen.n += 1
            contrato = registro.get("contrato") or ""
            resumen.contratos.add(contrato)
            recibido = registro["received_at"]
            resumen.dias.add(recibido[:10])
            if resumen.primera is None or recibido < resumen.primera:
                resumen.primera = recibido
            if resumen.ultima is None or recibido > resumen.ultima:
                resumen.ultima = recibido
            latencia = registro.get("latencia_s")
            if isinstance(latencia, (int, float)):
                resumen.latencias_s.append(float(latencia))

            clave = (flujo, registro.get("fuente", ""))
            previa = ultima_recepcion.get(clave)
            if previa is not None:
                separacion = (
                    desde_iso(recibido) - desde_iso(previa)
                ).total_seconds()
                if separacion >= 0:
                    resumen.separaciones_s.append(separacion)
            ultima_recepcion[clave] = recibido

            payload = registro.get("payload") or {}
            if flujo == "mercado":
                mercados_por_contrato[contrato].append(
                    {"received_at": recibido, "mercado": payload}
                )
            elif flujo == "libro":
                cuerpo = payload.get("cuerpo") or payload
                libros_por_contrato[contrato].append((recibido, cuerpo))
            elif flujo == "spot":
                precio = _precio_spot(registro.get("fuente", ""), payload)
                if precio is not None:
                    spot_por_fuente[registro.get("fuente", "?")].append(
                        (recibido, precio)
                    )
            elif flujo == "resultado":
                resultados[contrato] = payload

    # Estructura del libro y par libro/mercado.
    for contrato, libros in libros_por_contrato.items():
        mercados = mercados_por_contrato.get(contrato, [])
        for recibido, cuerpo in libros:
            try:
                libro = Libro.desde_payload(contrato, cuerpo, desde_iso(recibido))
            except Exception:  # noqa: BLE001
                estructura_libro["no_cuadra"] += 1
                continue
            estructura_libro["snapshots"] += 1
            # Control interno: compra de un lado + venta complementaria del otro
            # deben sumar 1000 mils por construccion.
            coherente = True
            for lado in (Lado.YES, Lado.NO):
                compra = libro.mejor_compra_mils(lado)
                venta = libro.mejor_venta_mils(lado.opuesto)
                if compra is not None and venta is not None and compra + venta != 1000:
                    coherente = False
            estructura_libro["cuadra" if coherente else "no_cuadra"] += 1

            # Par con la ficha de mercado mas cercana recibida antes.
            anteriores = [m for m in mercados if m["received_at"] <= recibido]
            if not anteriores:
                continue
            cercano = max(anteriores, key=lambda m: m["received_at"])
            problemas = libro.verificar_contra_mercado(cercano["mercado"])
            pares_libro_mercado["comparados"] += 1
            if problemas:
                pares_libro_mercado["discrepantes"] += 1
                separacion = (
                    desde_iso(recibido) - desde_iso(cercano["received_at"])
                ).total_seconds()
                if len(pares_libro_mercado["detalles"]) < 5:
                    pares_libro_mercado["detalles"].append(
                        {
                            "separacion_s": round(separacion, 3),
                            "problemas": list(problemas)[:2],
                        }
                    )

    # Brecha spot vs indice: el floor_strike de cada mercado es una lectura real
    # del indice (promedio de 60 s de apertura).
    # ``floor_strike`` es el promedio de 60 s del indice que termina en
    # ``open_time``. Para aislar la base indice-spot hay que comparar contra spot
    # de **esa misma ventana**; usar spot posterior mezclaria la base con la
    # deriva del precio desde la apertura, que es un efecto mucho mayor.
    ventana_base_s = 90.0
    base_por_fuente: dict[str, list[float]] = defaultdict(list)
    fuera_de_ventana = 0
    for contrato, entradas in mercados_por_contrato.items():
        umbral = None
        apertura = None
        for entrada in entradas:
            umbral = _a_decimal(entrada["mercado"].get("floor_strike"))
            crudo_apertura = entrada["mercado"].get("open_time")
            if umbral is not None and crudo_apertura:
                try:
                    apertura = desde_iso(crudo_apertura, "open_time")
                except Exception:  # noqa: BLE001
                    apertura = None
                break
        if umbral is None or apertura is None:
            continue
        for fuente, lecturas in spot_por_fuente.items():
            cercanas = [
                float(precio - umbral)
                for marca, precio in lecturas
                if abs((desde_iso(marca) - apertura).total_seconds()) <= ventana_base_s
            ]
            if cercanas:
                base_por_fuente[fuente].extend(cercanas)
            else:
                fuera_de_ventana += 1

    reporte = {
        "flujos": {
            nombre: resumen.como_dict(intervalos.get(nombre))
            for nombre, resumen in sorted(resumenes.items())
        },
        "controles": {
            "estructura_libro": estructura_libro,
            "par_libro_mercado": {
                "comparados": pares_libro_mercado["comparados"],
                "discrepantes": pares_libro_mercado["discrepantes"],
                "fraccion_discrepante": (
                    round(
                        pares_libro_mercado["discrepantes"]
                        / pares_libro_mercado["comparados"],
                        4,
                    )
                    if pares_libro_mercado["comparados"]
                    else None
                ),
                "ejemplos": pares_libro_mercado["detalles"],
                "lectura": (
                    "una discrepancia aqui es, tipicamente, antiguedad entre dos "
                    "lecturas HTTP, no error estructural; el control de estructura "
                    "lo distingue"
                ),
            },
            "base_spot_menos_indice_usd": {
                "ventana_s": ventana_base_s,
                "por_fuente": {
                    fuente: {
                        "n": len(valores),
                        "min": round(min(valores), 2),
                        "p50": round(statistics.median(valores), 2),
                        "max": round(max(valores), 2),
                    }
                    for fuente, valores in sorted(base_por_fuente.items())
                },
                "contratos_sin_spot_en_ventana": fuera_de_ventana,
                "lectura": (
                    "compara spot con el promedio de 60 s del indice que cierra "
                    "en open_time, usando solo spot de esa ventana; fuera de ella "
                    "la diferencia mezclaria la base con la deriva del precio"
                ),
            },
            "fuentes_spot": sorted(spot_por_fuente),
        },
        "etiquetas": {
            "contratos_con_resultado": len(resultados),
            "resultados": {
                contrato: {
                    "result": datos.get("result"),
                    "expiration_value": datos.get("expiration_value"),
                }
                for contrato, datos in sorted(resultados.items())
            },
        },
    }
    return reporte


def suficiente_para(reporte: dict, minimos: dict) -> tuple[bool, tuple[str, ...]]:
    """Comprueba el reporte contra minimos declarados.

    ``minimos`` se fija **antes** de mirar los datos. Devuelve los motivos por
    los que los datos no alcanzan, que es la informacion que decide si una fase
    puede continuar.
    """
    motivos: list[str] = []
    for flujo, exigido in (minimos.get("observaciones_por_flujo") or {}).items():
        presente = (reporte["flujos"].get(flujo) or {}).get("n", 0)
        if presente < exigido:
            motivos.append(f"flujo {flujo}: {presente} observaciones < {exigido}")
    exigidos_contratos = minimos.get("contratos_con_resultado")
    if exigidos_contratos is not None:
        presente = reporte["etiquetas"]["contratos_con_resultado"]
        if presente < exigidos_contratos:
            motivos.append(
                f"contratos con resultado: {presente} < {exigidos_contratos}"
            )
    estructura = reporte["controles"]["estructura_libro"]
    if estructura["snapshots"] and estructura["no_cuadra"]:
        motivos.append(
            f"estructura del libro no cuadra en {estructura['no_cuadra']} "
            f"de {estructura['snapshots']} snapshots"
        )
    return (not motivos), tuple(motivos)
