.PHONY: lint lint-ci
lint:
	$(call run_ruff,.)

lint-ci:
	uv run ruff check .

define run_ruff
	@echo "\n=== Running ruff on $(1) ==="; \
	echo "Running ruff format in $(1)"; \
	(cd $(1) && uv run ruff format .) || { echo "FAILED: ruff format in $(1)"; exit 1; }; \
	echo "Running ruff check --fix in $(1)"; \
	(cd $(1) && uv run ruff check --fix .) || { echo "FAILED: ruff check in $(1)"; exit 1; }; \
	echo "=== ruff completed successfully for $(1) ===";
endef