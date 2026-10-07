#!/usr/bin/env python3
"""Servidor LOCAL do Controle de Obra (SQLite em data/obra.db). Uso: python3 server.py [porta]
Em produção (Vercel) quem atende /api/* é api/index.py, com PostgreSQL."""
import os, sys
BASE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(BASE, 'api'))
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from _core import handle

class H(SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=os.path.join(BASE, 'public'), **k)
    def log_message(s, *a): pass
    def route(s, m):
        if not s.path.startswith('/api/'): return False
        raw = s.rfile.read(int(s.headers.get('Content-Length') or 0))
        code, h, b = handle(m, s.path, s.headers.get('Cookie', ''), s.headers.get('Content-Type', ''), raw)
        s.send_response(code); h['Content-Length'] = str(len(b))
        for k, v in h.items(): s.send_header(k, v)
        s.end_headers(); s.wfile.write(b); return True
    def do_GET(s): s.route('GET') or super().do_GET()
    def do_POST(s): s.route('POST')
    def do_PUT(s): s.route('PUT')
    def do_DELETE(s): s.route('DELETE')

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f'Controle de Obra em http://localhost:{port}  (Ctrl+C para sair)')
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
