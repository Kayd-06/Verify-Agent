#!/usr/bin/env python3
"""
Verity Dashboard Server
Serves the project root as static files + provides /api/* endpoints
for reading shared/action_log.jsonl and shared/verifications.jsonl live.
"""
import json
import os
import sys
import time
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(BASE, "shared")

# Make sure eval is in path
sys.path.insert(0, BASE)
from eval.run_eval import run_eval

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
        elif parsed.path == "/api/demo/quick":
            self._trigger_demo("quick")
        elif parsed.path == "/api/demo/inject":
            self._trigger_demo("inject")
        elif parsed.path == "/api/demo/full_demo":
            self._trigger_demo("full_demo")
        elif parsed.path == "/api/demo/reset_full":
            self._trigger_demo("full_reset")
        elif parsed.path == "/api/stream":
            self._stream()
        else:
            # Strip /landing prefix if coming from landing
            super().do_GET()

    def _trigger_demo(self, mode):
        # run eval in background
        threading.Thread(target=run_eval, args=(mode,)).start()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"status": "started"}')

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        while True:
            # Gather all state
            state = {
                "actions": self._read_jsonl("action_log.jsonl"),
                "verifications": self._read_jsonl("verifications.jsonl"),
                "notion_db": self._read_json_file("notion_db.json"),
                "slack_db": self._read_json_file("slack_db.json")
            }
            try:
                msg = f"data: {json.dumps(state)}\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
                time.sleep(1)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                break
            except Exception:
                time.sleep(1)

    def _read_jsonl(self, filename):
        path = os.path.join(SHARED, filename)
        rows = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                rows.append(json.loads(line))
                            except Exception:
                                pass
            except Exception:
                pass
        return rows

    def _send_jsonl(self, filename):
        rows = self._read_jsonl(filename)
        body = json.dumps(rows).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_file(self, filename):
        path = os.path.join(SHARED, filename)
        data = {}
        if os.path.exists(path):
            # Retries for locking / thread-safety during truncation
            for _ in range(5):
                try:
                    with open(path) as f:
                        data = json.load(f)
                        break
                except json.JSONDecodeError:
                    time.sleep(0.1)
                except Exception:
                    time.sleep(0.1)
        return data

    def _send_json_file(self, filename):
        data = self._read_json_file(filename)
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_eval_results(self):
        verifications = self._read_jsonl("verifications.jsonl")
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
    server = ThreadingHTTPServer(("", port), VerityHandler)
    print(f"Verity server running at http://localhost:{port}")
    print(f"  Landing page -> http://localhost:{port}/landing/")
    print(f"  Dashboard    -> http://localhost:{port}/dashboard/")
    server.serve_forever()
