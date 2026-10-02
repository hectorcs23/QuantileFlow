PYTHON ?= python3
DOC := docs/propuesta

.PHONY: todo test figuras pdf limpiar verificar piloto-sintetico estrategias-sinteticas

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

estrategias-sinteticas:
	$(PYTHON) scripts/estrategias_sintetico.py

limpiar:
	cd $(DOC) && latexmk -C main.tex
	rm -rf .pytest_cache $(DOC)/figuras_src/__pycache__ quantileflow/__pycache__ \
		estrategias/__pycache__ tests/__pycache__
