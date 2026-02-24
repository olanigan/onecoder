.PHONY: test typecheck health clean

test:
	uv run pytest tests/

typecheck:
	uvx ty check

health:
	@echo "Running full code health check..."
	@make -s typecheck || (echo "❌ Type check failed" && exit 1)
	@make -s test || (echo "❌ Tests failed" && exit 1)
	@echo "✅ Code health is excellent!"

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} +
	rm -rf .pytest_cache .venv
