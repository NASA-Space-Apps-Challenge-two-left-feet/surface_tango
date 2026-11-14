# Replace the `prewarm` target in Makefile with:
prewarm: ## Discover 2026 NISAR granules over Antioquia and slice them into the local Zarr v3 Data Cube
	$(COMPOSE) build cache-warmer
	$(COMPOSE) run --rm cache-warmer sh -c "python scripts/discover_nisar_colombia.py && python scripts/prewarm_antioquia_cache.py"
