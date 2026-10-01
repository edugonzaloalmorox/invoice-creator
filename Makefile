.PHONY: run backend frontend kill-ports

# Local development defaults. Existing environment values take precedence.
export INVOICE_ENVIRONMENT ?= development
export INVOICE_FRONTEND_ORIGIN ?= http://localhost:3000
export GOOGLE_CREDENTIALS_REFERENCE ?= fixture://local
export GOOGLE_TEMPLATE_ID ?= fixture-template
export INVOICE_MAX_REQUEST_BYTES ?= 1048576
export INVOICE_MAX_RESPONSE_BYTES ?= 5242880
export GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS ?= 3
export GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS ?= 10

kill-ports:
	@for port in 8000 3000; do \
		pids=$$(lsof -tiTCP:$$port -sTCP:LISTEN 2>/dev/null || true); \
		if [ -n "$$pids" ]; then \
			echo "Stopping processes on port $$port: $$pids"; \
			kill -9 $$pids 2>/dev/null || true; \
		fi; \
	done

backend:
	uv run python -m backend.run

frontend:
	npm --prefix frontend start

run: kill-ports
	$(MAKE) backend & backend_pid=$$!; \
	trap 'kill $$backend_pid 2>/dev/null || true' 0 2 15; \
	$(MAKE) frontend
