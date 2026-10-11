.PHONY: demo setup test notebook clean

demo: ## the 10-minute path
	uv run demo

setup:
	uv sync

test:
	uv sync --extra dev
	uv run pytest -q

notebook:
	uv sync --extra notebook
	uv run jupyter nbconvert --to notebook --execute demo.ipynb --output demo.out.ipynb

clean:
	rm -rf cache demo.out.ipynb
