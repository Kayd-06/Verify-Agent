#!/usr/bin/env python3
"""
Verity Dashboard Server
Serves the project root as static files + provides /api/* endpoints
for reading shared/action_log.jsonl and shared/verifications.jsonl live.
"""
import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(BASE, "shared")


class VerityHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        # API routes
        if parsed.path == "/api/actions":
            self._send_jsonl("action_log.jsonl")
        elif parsed.path == "/api/verifications":
            self._send_jsonl("verifications.jsonl")
        elif parsed.path == "/api/notion_db":
            self._send_json_file("notion_db.json")
        elif parsed.path == "/api/slack_db":
            self._send_json_file("slack_db.json")
        else:
            # Strip /landing prefix if coming from landing
            super().do_GET()

    def _send_jsonl(self, filename):
        path = os.path.join(SHARED, filename)
        rows = []
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        body = json.dumps(rows).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json_file(self, filename):
        path = os.path.join(SHARED, filename)
        data = {}
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # silence


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7777
    server = HTTPServer(("", port), VerityHandler)
    print(f"Verity server running at http://localhost:{port}")
    print(f"  Landing page → http://localhost:{port}/landing/")
    print(f"  Dashboard    → http://localhost:{port}/dashboard/")
    server.serve_forever()
