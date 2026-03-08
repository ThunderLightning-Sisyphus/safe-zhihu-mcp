.PHONY: install run run-visible test test-unit lint

install:
	pip install -r requirements.txt
	playwright install chromium

run:
	HEADLESS=true python3 mcp_server.py

run-visible:
	HEADLESS=false python3 mcp_server.py

test:
	python3 mcp_server.py --test

test-unit:
	python3 -m pytest tests/ -v

lint:
	python3 -m ruff check zhihu_mcp/ mcp_server.py || true
