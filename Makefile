.PHONY: test typecheck health clean coverage cov-report

test:
	uv run pytest tests/

typecheck:
	uvx ty check

coverage:
	uv run pytest --cov=onecoder tests/

cov-report:
	uv run pytest --cov=onecoder --cov-report=html tests/
	@echo "Report generated in htmlcov/index.html"

health:
	@echo "Running full code health check..."
	@make -s typecheck || (echo "❌ Type check failed" && exit 1)
	@make -s test || (echo "❌ Tests failed" && exit 1)
	@make -s coverage || (echo "❌ Coverage check failed" && exit 1)
	@echo "✅ Code health is excellent!"

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} +
	rm -rf .pytest_cache .venv
