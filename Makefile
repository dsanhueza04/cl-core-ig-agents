SHELL       := /bin/bash
IMAGE       ?= cl-core-ig-agents/ig-tools:dev
IG          ?= examples/demo/gold
CACHE_VOL   ?= clcore-fhir-cache
CLCORE_TGZ  ?= reference/clcore-1.9.3/site/package.tgz
PYTHON      ?= python3

.DEFAULT_GOAL := help
.PHONY: help build validate catalog test shell clean-cache

help: ## Lista los comandos
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

build: ## Construye la imagen con SUSHI, IG Publisher y Jekyll
	docker build -t $(IMAGE) -f docker/Dockerfile docker

validate: ## Compila con SUSHI y corre el IG Publisher sobre IG=<carpeta>
	@test -f "$(IG)/sushi-config.yaml" || { echo "No existe $(IG)/sushi-config.yaml"; exit 1; }
	@test -f "$(CLCORE_TGZ)" || { echo "Falta $(CLCORE_TGZ) (ver reference/README.md)"; exit 1; }
	docker run --rm \
	  -v "$(CURDIR)/$(IG):/ig" \
	  -v "$(CURDIR)/$(CLCORE_TGZ):/reference/clcore.tgz:ro" \
	  -v $(CACHE_VOL):/root/.fhir \
	  $(IMAGE)

catalog: ## Extrae el catálogo de CL Core (build/catalog/) para los agentes
	$(PYTHON) scripts/extract_catalog.py --package $(CLCORE_TGZ) --out build/catalog

test: ## Corre las pruebas
	$(PYTHON) -m pytest -q

shell: ## Abre una terminal dentro del contenedor (depuración)
	docker run --rm -it --entrypoint bash \
	  -v "$(CURDIR):/work" -v $(CACHE_VOL):/root/.fhir $(IMAGE)

clean-cache: ## Borra la caché de paquetes FHIR del contenedor
	docker volume rm $(CACHE_VOL)
