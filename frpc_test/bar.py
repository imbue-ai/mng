from http.server import *


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hello from BAR")


HTTPServer(("0.0.0.0", 9002), H).serve_forever()
