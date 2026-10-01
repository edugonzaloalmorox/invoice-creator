"""Development-only WSGI entry point for the invoice filler backend."""

from wsgiref.simple_server import make_server

from .app.main import app


if __name__ == "__main__":
    with make_server("127.0.0.1", 8000, app) as server:
        print("invoice-filler backend listening on http://127.0.0.1:8000")
        server.serve_forever()
