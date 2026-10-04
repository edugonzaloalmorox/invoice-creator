.PHONY: run backend frontend kill-ports

# Load optional local configuration. Keep real credentials in .env; it is ignored
# by Git. Explicit command-line assignments still take precedence.
-include .env

# Local development defaults.
INVOICE_ENVIRONMENT ?= development
INVOICE_FRONTEND_ORIGIN ?= http://localhost:3000
GOOGLE_CREDENTIALS_REFERENCE ?= fixture://local
GOOGLE_TEMPLATE_ID ?= fixture-template
INVOICE_MAX_REQUEST_BYTES ?= 1048576
INVOICE_MAX_RESPONSE_BYTES ?= 5242880
GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS ?= 3
GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS ?= 10
GOOGLE_OAUTH_CLIENT_ID ?=
GOOGLE_OAUTH_CLIENT_SECRET ?=
GOOGLE_OAUTH_REDIRECT_URI ?=
GOOGLE_OAUTH_SCOPES ?= openid email https://www.googleapis.com/auth/documents https://www.googleapis.com/auth/drive.file
SESSION_SECRET ?=

export INVOICE_ENVIRONMENT INVOICE_FRONTEND_ORIGIN \
	GOOGLE_CREDENTIALS_REFERENCE GOOGLE_TEMPLATE_ID \
	INVOICE_MAX_REQUEST_BYTES INVOICE_MAX_RESPONSE_BYTES \
	GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS \
	GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_REDIRECT_URI \
	GOOGLE_OAUTH_SCOPES SESSION_SECRET

kill-ports:
	@for port in 8000 3000; do \
		pids=$$(lsof -tiTCP:$$port -sTCP:LISTEN 2>/dev/null || true); \
		if [ -n "$$pids" ]; then \
			echo "Stopping processes on port $$port: $$pids"; \
			kill -9 $$pids 2>/dev/null || true; \
		fi; \
		attempt=0; \
		while [ "$$attempt" -lt 20 ] && [ -n "$$(lsof -tiTCP:$$port -sTCP:LISTEN 2>/dev/null || true)" ]; do \
			sleep 0.1; \
			attempt=$$((attempt + 1)); \
		done; \
		if [ -n "$$(lsof -tiTCP:$$port -sTCP:LISTEN 2>/dev/null || true)" ]; then \
			echo "Port $$port is still in use." >&2; \
			exit 1; \
		fi; \
	done

backend:
	uv run python -m backend.run

frontend:
	npm --prefix frontend start

run: kill-ports
	INVOICE_ENVIRONMENT=development INVOICE_FRONTEND_ORIGIN=http://localhost:3000 uv run python -m backend.run & \
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
