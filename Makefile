PYTHON ?= python3
DOC := docs/propuesta

.PHONY: todo test figuras pdf limpiar verificar piloto-sintetico captura captura-prueba \
	historico-alpaca normalizar-alpaca verificar-alpaca

todo: test figuras pdf

test:
	$(PYTHON) -m pytest -q

figuras:
	$(PYTHON) $(DOC)/figuras_src/generar.py

pdf:
	cd $(DOC) && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	cp $(DOC)/main.pdf docs/QuantileFlow_propuesta_tecnica.pdf

verificar:
	$(PYTHON) scripts/verificar_entorno.py

piloto-sintetico:
	$(PYTHON) scripts/piloto_sintetico.py

# Captura diaria en Alpaca (requiere APCA_API_KEY_ID y APCA_API_SECRET_KEY); espera hasta 09:45 y 10:00 ET.
captura:
	$(PYTHON) scripts/capturar_alpaca.py

# Captura inmediata de prueba (fuera de sesión usa las últimas cotizaciones de la sesión anterior).
captura-prueba:
	$(PYTHON) scripts/capturar_alpaca.py --ahora

# Precio del objetivo (SIP de SPY, pasados 15 minutos de cada corte) y eventos corporativos; completa lo que falte.
historico-alpaca:
	$(PYTHON) scripts/historico_alpaca.py

# make normalizar-alpaca DESDE=AAAA-MM-DD HASTA=AAAA-MM-DD
normalizar-alpaca:
	$(PYTHON) scripts/normalizar_alpaca.py --desde $(DESDE) --hasta $(HASTA)

# make verificar-alpaca FECHA=AAAA-MM-DD
verificar-alpaca:
	$(PYTHON) scripts/verificar_alpaca.py --fecha $(FECHA)

limpiar:
	cd $(DOC) && latexmk -C main.tex
	rm -rf .pytest_cache $(DOC)/figuras_src/__pycache__ quantileflow/__pycache__ tests/__pycache__
