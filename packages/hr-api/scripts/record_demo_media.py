#!/usr/bin/env python3
"""Regenerate demo/media/part-*.webm from a browser, reproducibly.

    python scripts/record_demo_media.py            # serves on :8765
    then open http://localhost:8765/ and press the button

WHY THIS EXISTS
The demo WebM files were committed with no way to make them again, and the
footage had a specific candidate's NAME AND JOB TITLE burned into the pixels.
Attaching it to any other interview therefore put the wrong person's name on the
recruiter's flagship screen -- a Senior Platform Engineer's review page playing
a video captioned "CDL Driver". In front of a buyer that is worse than showing
no video at all.

The replacement footage is anonymous, so it can be attached to whichever
interview the demo needs, and it is REAL MediaRecorder output rather than a
synthesised container: everything after getUserMedia -- the recorder, the
container, the upload, the duration repair, the storage, the range serving and
the player -- is the same code a live capture takes.
"""
from __future__ import annotations

import argparse
import http.server
import pathlib
import socketserver

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "demo" / "generate_media.html"
OUT = ROOT / "demo" / "media"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):                                   # noqa: N802
        if self.path.split("?")[0] in ("/", "/index.html"):
            body = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):                                  # noqa: N802
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        part = int(q.get("part", ["0"])[0])
        if not 1 <= part <= 99:
            self.send_error(400, "part out of range")
            return
        n = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(n)
        OUT.mkdir(parents=True, exist_ok=True)
        dest = OUT / f"part-{part:03d}.webm"
        dest.write_bytes(data)
        msg = f"{dest.name} ({len(data)} bytes)".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)
        print(f"  wrote {dest} ({len(data)} bytes)")

    def log_message(self, *a):                          # quieter
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
        print(f"open http://localhost:{args.port}/ and press the button")
        print(f"parts will be written to {OUT}")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
