"""Função serverless da Vercel: toda rota /api/* chega aqui (ver vercel.json)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import BaseHTTPRequestHandler
from _core import handle

class handler(BaseHTTPRequestHandler):
    def _go(self, m):
        raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        code, h, body = handle(m, self.path, self.headers.get('Cookie', ''), self.headers.get('Content-Type', ''), raw)
        self.send_response(code); h['Content-Length'] = str(len(body))
        for k, v in h.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)
    def do_GET(self): self._go('GET')
    def do_POST(self): self._go('POST')
    def do_PUT(self): self._go('PUT')
    def do_DELETE(self): self._go('DELETE')
