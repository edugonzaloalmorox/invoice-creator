"""Development-only WSGI entry point for the invoice filler backend."""

import logging
from wsgiref.simple_server import WSGIRequestHandler, make_server

from .app.main import app


def redact_request_line(request_line: str) -> str:
    """Remove query strings from access-log request lines."""

    parts = request_line.split(" ", 2)
    if len(parts) != 3:
        return request_line
    method, target, version = parts
    return f"{method} {target.split('?', 1)[0]} {version}"


class RedactingRequestHandler(WSGIRequestHandler):
    """Keep OAuth codes and other query values out of development logs."""

    def log_message(self, format, *args):
        """Redact query strings before delegating the access log message."""

        safe_args = list(args)
        if safe_args and isinstance(safe_args[0], str):
            safe_args[0] = redact_request_line(safe_args[0])
        super().log_message(format, *safe_args)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    with make_server("127.0.0.1", 8000, app, handler_class=RedactingRequestHandler) as server:
        print("invoice-filler backend listening on http://127.0.0.1:8000")
        server.serve_forever()
