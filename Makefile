.PHONY: run backend frontend kill-ports

# Local development defaults. Existing environment values take precedence.
export INVOICE_ENVIRONMENT ?= development
export INVOICE_FRONTEND_ORIGIN ?= http://127.0.0.1:3000
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
	uv run python -m backend.run & \
	backend_pid=$$!; \
	cleanup() { kill "$$backend_pid" 2>/dev/null || true; wait "$$backend_pid" 2>/dev/null || true; }; \
	trap cleanup 0 2 15; \
	backend_ready=0; \
	attempt=0; \
	while [ "$$attempt" -lt 50 ]; do \
		if curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null 2>&1; then \
			backend_ready=1; \
			break; \
		fi; \
		if ! kill -0 "$$backend_pid" 2>/dev/null; then \
			echo "Backend stopped before it became ready." >&2; \
			exit 1; \
		fi; \
		sleep 0.1; \
		attempt=$$((attempt + 1)); \
	done; \
	if [ "$$backend_ready" -ne 1 ]; then \
		echo "Backend did not become ready on port 8000." >&2; \
		exit 1; \
	fi; \
	npm --prefix frontend start
