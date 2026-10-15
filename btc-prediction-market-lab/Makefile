.PHONY: ayuda pruebas capacidades capturar cobertura demo limpiar

ayuda:
	@echo "pruebas      - ejecuta la bateria de pruebas"
	@echo "capacidades  - reaudita las capacidades en vivo y reescribe el reporte"
	@echo "capturar     - captura prospectiva (CAPTURA_S segundos, por omision 600)"
	@echo "cobertura    - reporte de cobertura del almacen"
	@echo "demo         - cadena completa sobre un mercado en vivo, sin ordenes"
	@echo "limpiar      - borra cache de Python y datos de demostracion"

pruebas:
	python3 -m pytest tests/ -q

capacidades:
	python3 scripts/auditar_capacidades.py --salida reportes/capacidades.json

CAPTURA_S ?= 600
capturar:
	python3 scripts/capturar.py --duracion $(CAPTURA_S) --periodo 5 --raiz datos/captura

cobertura:
	python3 scripts/auditar_cobertura.py --raiz datos/captura --salida reportes/cobertura.json

demo:
	python3 scripts/demo_decision.py

limpiar:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
	rm -rf datos/captura_demo datos/decisiones
