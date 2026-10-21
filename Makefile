PYTHON ?= python3
DOC := docs/propuesta

.PHONY: all test figures pdf clean verify synthetic-pilot

all: test figures pdf

test:
	$(PYTHON) -m pytest -q

figures:
	$(PYTHON) $(DOC)/figuras_src/generar.py

pdf:
	cd $(DOC) && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	cp $(DOC)/main.pdf docs/QuantileFlow_propuesta_tecnica.pdf

verify:
	$(PYTHON) scripts/verify_environment.py

synthetic-pilot:
	$(PYTHON) scripts/synthetic_pilot.py

clean:
	cd $(DOC) && latexmk -C main.tex
	rm -rf .pytest_cache $(DOC)/figuras_src/__pycache__ quantileflow/__pycache__ tests/__pycache__
