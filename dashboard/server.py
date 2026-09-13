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
        elif parsed.path == "/api/eval_results":
            self._send_eval_results()
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

    def _send_eval_results(self):
        """Compute live accuracy metrics from verifications.jsonl."""
        verif_path = os.path.join(SHARED, "verifications.jsonl")
        verifications = []
        if os.path.exists(verif_path):
            with open(verif_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            verifications.append(json.loads(line))
                        except Exception:
                            pass
        total = len(verifications)
        pass_count  = sum(1 for v in verifications if v.get("result") == "PASS")
        fail_count  = sum(1 for v in verifications if v.get("result") == "FAIL")
        auto_fixed  = sum(1 for v in verifications if v.get("remediation") == "reverted")
        escalated   = sum(1 for v in verifications if v.get("remediation") == "escalated")
        latencies   = [v.get("latency_ms", 0) for v in verifications if v.get("latency_ms")]
        avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
        pass_rate   = round((pass_count / total * 100), 1) if total else None

        data = {
            "total": total,
            "pass": pass_count,
            "fail": fail_count,
            "auto_fixed": auto_fixed,
            "escalated": escalated,
            "pass_rate": pass_rate,
            "avg_latency_ms": avg_latency,
        }
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
    print(f"  Landing page -> http://localhost:{port}/landing/")
    print(f"  Dashboard    -> http://localhost:{port}/dashboard/")
    server.serve_forever()
