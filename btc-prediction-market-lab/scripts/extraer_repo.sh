#!/usr/bin/env bash
# Crea el repositorio independiente de este proyecto, con su propia historia.
#
# La sesion que genero este proyecto NO pudo crear un repositorio nuevo en
# GitHub: el proxy limita el token a los repositorios configurados y devuelve
# 403 ("sessions are bound to their configured repositories"). Por eso el
# proyecto vive en una carpeta autocontenida y este script lo extrae.
#
# Uso:
#   bash scripts/extraer_repo.sh [destino]
#
# Despues, para publicarlo:
#   gh repo create btc-prediction-market-lab --private --source=<destino> --push
# o bien, sin gh:
#   1) crear el repositorio vacio en github.com
#   2) cd <destino>
#      git remote add origin git@github.com:<usuario>/btc-prediction-market-lab.git
#      git push -u origin main

set -euo pipefail

ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINO="${1:-$HOME/btc-prediction-market-lab}"

if [ -e "$DESTINO" ]; then
  echo "error: $DESTINO ya existe; elija otro destino o borrelo" >&2
  exit 1
fi

echo "copiando desde $ORIGEN"
mkdir -p "$DESTINO"

# Se copia el arbol de trabajo sin datos capturados ni cache.
tar -C "$ORIGEN" \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='datos/captura*' \
    --exclude='datos/decisiones' \
    --exclude='*.egg-info' \
    -cf - . | tar -C "$DESTINO" -xf -

cd "$DESTINO"
git init -q -b main
git add -A
git commit -q -m "Laboratorio de investigacion para mercados de prediccion de BTC

Fases A y B de la metodologia: auditoria de capacidades con evidencia
reproducible, ficha de contrato verificada contra los terminos oficiales,
capturador prospectivo con control de tasa, almacen por anadido con
manifiesto y auditoria de cobertura. Incluye la cadena de costes
ejecutables, probabilidad conservadora, sizing con busqueda discreta y
replay con latencia y profundidad.

Estado: DATA_ONLY. Sin ventaja medida y sin importes sugeridos."

echo
echo "repositorio independiente creado en $DESTINO"
echo "pruebas:  cd $DESTINO && python3 -m pytest tests/ -q"
echo
echo "para publicarlo en GitHub:"
echo "  gh repo create btc-prediction-market-lab --private --source=$DESTINO --push"
