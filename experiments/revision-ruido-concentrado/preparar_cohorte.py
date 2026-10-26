"""Arma las entradas de cualquier rango de fechas con el preparador de la rama revisada.

Copia experiments/ruido_concentrado_20261022/preparar_nuevos.py de la rama, cambia solo el rango de
fechas y dónde escribe su resumen, y lo corre. Así la cohorte conocida (2 al 9 de octubre) sale del
mismo código que la nueva.

Uso::

    python experiments/revision-ruido-concentrado/preparar_cohorte.py --rama RAMA --tablas TABLAS \
        --crudo DATOS --privado PRIVADO/entradas --resumen PRIVADO/entradas.json --desde 2026-10-02 --hasta 2026-10-09
"""
import argparse
from pathlib import Path
import runpy
import sys

CAMBIOS = [
    ("for n in ('tablas','crudo','privado'): ap.add_argument('--'+n,type=Path,required=True)",
     "for n in ('tablas','crudo','privado','resumen'): ap.add_argument('--'+n,type=Path,required=True)\n"
     "    ap.add_argument('--desde',required=True); ap.add_argument('--hasta',required=True)"),
    ("pd.date_range(proto['nuevos_desde'],proto['nuevos_hasta'],freq='B')", "pd.date_range(a.desde,a.hasta,freq='B')"),
    ("dump(out/'entradas_nuevas.json',", "dump(a.resumen,"),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rama", type=Path, required=True, help="checkout de codex/ruido-concentrado-20261022")
    a, resto = ap.parse_known_args()
    carpeta = a.rama.resolve()/"experiments"/"ruido_concentrado_20261022"
    texto = (carpeta/"preparar_nuevos.py").read_text(encoding="utf-8")
    for viejo, nuevo in CAMBIOS:
        if texto.count(viejo) != 1:
            raise ValueError(f"el preparador cambió: {viejo[:40]}")
        texto = texto.replace(viejo, nuevo)
    copia = carpeta/"_preparar_cohorte.py"  # junto al original, para que RAIZ y las importaciones no cambien
    copia.write_text(texto, encoding="utf-8")
    try:
        sys.argv = [str(copia), *resto]
        runpy.run_path(str(copia), run_name="__main__")
    finally:
        copia.unlink()


if __name__ == "__main__":
    main()
