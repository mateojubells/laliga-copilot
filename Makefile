SHELL := /bin/bash
ROOT := $(shell pwd)
export PATH := $(ROOT)/.tools/bin:$(ROOT)/.tools/node/bin:$(PATH)
PY := .venv/bin/python

.PHONY: bootstrap dev test eval eval-test data reference clean

bootstrap:            ## instala uv, Node, ffmpeg y dependencias (sin sudo)
	@./scripts/bootstrap.sh

dev: bootstrap        ## instala lo necesario y arranca backend + frontend
	@./scripts/dev.sh

test: bootstrap       ## tests de Python (y del frontend si existe)
	@$(PY) -m pytest -q
	@if [ -f web/package.json ]; then cd web && npm test --silent; fi

eval:                 ## tabla de métricas sobre dev -> eval/history/
	@$(PY) -m eval.run_eval --split dev $(ARGS)

eval-test:            ## igual sobre test (solo para informes; no mirar errores frase a frase)
	@$(PY) -m eval.run_eval --split test $(ARGS)

data:                 ## regenera los datos sintéticos (semilla fija)
	@$(PY) -m data.synth.generate

reference:            ## transcripción de referencia del audio real (proceso pesado)
	@$(PY) -m eval.scripts.make_reference
