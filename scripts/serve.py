#!/usr/bin/env python3
"""Serve the dashboard locally: python3 scripts/serve.py [port]"""
import functools
import http.server
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
with socketserver.TCPServer(("", PORT), handler) as httpd:
    print(f"Dashboard: http://localhost:{PORT}/dashboard/index.html  (ctrl-c to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
