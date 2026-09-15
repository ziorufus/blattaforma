#!/usr/bin/env python3
"""Local helper for the Blattaforma "macos-daemons" module.

Runs as the same unprivileged user as the machine's nginx (e.g. `alessio`),
bound to 127.0.0.1 only. It is reached exclusively through nginx, which has
already authenticated the request (auth_request against the central
Blattaforma backend) and validated the shape of its JSON body. This service
does not itself decide which daemons/actions are legitimate -- it only
forwards to `sudo -n bin/daemonctl`, which owns the real, root-only
whitelist. Stdlib only, no third-party dependencies.
"""

import json
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8765

DAEMONCTL = "/opt/blattaforma-daemons/bin/daemonctl"
ACTIONS = {"start", "stop", "enable", "disable", "status"}
LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SUDO_TIMEOUT = 15


class Handler(BaseHTTPRequestHandler):
    server_version = "blattaforma-macos-daemons-helper/1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        action = self.path.strip("/")
        if action not in ACTIONS:
            self._send_json(404, {"error": "unknown action"})
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return

        label = data.get("label") if isinstance(data, dict) else None
        if not isinstance(label, str) or not LABEL_RE.match(label):
            self._send_json(400, {"error": "invalid label"})
            return

        try:
            result = subprocess.run(
                ["sudo", "-n", DAEMONCTL, action, label],
                capture_output=True,
                text=True,
                timeout=SUDO_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            self._send_json(504, {"error": "daemonctl timed out"})
            return

        stdout = result.stdout.strip()
        if result.returncode == 0 and stdout:
            try:
                self._send_json(200, json.loads(stdout))
                return
            except json.JSONDecodeError:
                pass

        self._send_json(
            200,
            {
                "success": result.returncode == 0,
                "stdout": stdout,
                "stderr": result.stderr.strip(),
            },
        )

    def do_GET(self):
        self._send_json(404, {"error": "use POST"})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
