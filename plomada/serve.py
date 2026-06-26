"""serve — sirve el reporte HTML en 127.0.0.1 (solo localhost, sin red externa)."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve_html(html_text, port=8770, host="127.0.0.1"):
    body = html_text.encode("utf-8")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer((host, port), H)
    print(f"plomada · http://{host}:{port}  (Ctrl-C para parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n— detenido —")
