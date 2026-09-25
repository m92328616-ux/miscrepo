#!/usr/bin/env python3
"""htmlviewer.py — view files as interactive, scrollable web pages.

	Usage:
		python3 htmlviewer.py                # start the app, import files in the browser
		python3 htmlviewer.py somefile.txt   # open a file right away (any port/host too)

	This starts a small local server that serves ``viewer.html`` (the client
	app).  The app has an Import button and drag-and-drop: pick a file and it
	is posted to /import, then delivered back through /doc/<id>.  HTML files
	are rendered as-is by the browser; every other file becomes an interactive
	scrollable page with line numbers, a match-counting search (Enter to jump
	between hits), wrap toggle, and zoom.  Your browser is opened automatically.
"""

import argparse
import json
import pathlib
import re
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

_HTML_EXTENSIONS = {".html", ".htm", ".xhtml"}
_DOCS_DIR = pathlib.Path(__file__).with_name(".htmlviewer_docs")
_INDEX_FILE = _DOCS_DIR / "index.json"


def _looks_like_html(name: str, text: str) -> bool:
	"""True when the document should be handed to the browser as-is."""
	if pathlib.PurePath(name).suffix.lower() in _HTML_EXTENSIONS:
		return True
	head = text.lstrip()[:200].lower()
	return head.startswith("<!doctype") or head.startswith("<html")


@dataclass
class _Doc:
	name: str
	body: bytes
	is_html: bool


def _persist_doc(doc_id: str, doc: _Doc) -> None:
	"""Best-effort save so imports survive the server stopping."""
	try:
		_DOCS_DIR.mkdir(parents=True, exist_ok=True)
		(_DOCS_DIR / doc_id).write_bytes(doc.body)
		if _INDEX_FILE.is_file():
			index = json.loads(_INDEX_FILE.read_text("utf-8"))
		else:
			index = {}
		index[doc_id] = {"name": doc.name, "is_html": doc.is_html}
		tmp = _INDEX_FILE.with_suffix(".tmp")
		tmp.write_text(json.dumps(index, ensure_ascii=False))
		tmp.replace(_INDEX_FILE)
	except OSError:
		pass


def _load_persisted_docs() -> tuple[dict[str, _Doc], int]:
	"""Restore previously imported docs from disk; returns (docs, next_counter)."""
	docs: dict[str, _Doc] = {}
	next_counter = 0
	try:
		index = json.loads(_INDEX_FILE.read_text("utf-8"))
	except (OSError, ValueError):
		return docs, next_counter
	for doc_id, meta in index.items():
		try:
			body = (_DOCS_DIR / doc_id).read_bytes()
		except OSError:
			continue
		docs[doc_id] = _Doc(str(meta.get("name", "")), body, bool(meta.get("is_html", False)))
		match = re.fullmatch(r"doc(\d+)", doc_id)
		if match:
			next_counter = max(next_counter, int(match.group(1)))
	return docs, next_counter


class _ViewerHTTPServer(ThreadingHTTPServer):
	app_html: bytes
	docs: dict[str, _Doc]
	counter: int


class _ViewerHandler(BaseHTTPRequestHandler):
	server_version = "htmlviewer"

	@property
	def _server(self) -> _ViewerHTTPServer:
		return cast(_ViewerHTTPServer, self.server)

	def _send_bytes(self, status: int, body: bytes, content_type: str, extra_headers=()):
		self.send_response(status)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(len(body)))
		self.send_header("Cache-Control", "no-store")
		for key, value in extra_headers:
			self.send_header(key, value)
		self.end_headers()
		self.wfile.write(body)

	def do_GET(self):
		srv = self._server
		path = self.path.split("?", 1)[0]
		if path in ("/", ""):
			self._send_bytes(200, srv.app_html, "text/html; charset=utf-8")
			return
		if path.startswith("/doc/"):
			doc = srv.docs.get(urllib.parse.unquote(path[len("/doc/"):]))
			if doc is None:
				self._send_bytes(404, b"unknown document", "text/plain; charset=utf-8")
				return
			ctype = "text/html; charset=utf-8" if doc.is_html else "text/plain; charset=utf-8"
			self._send_bytes(200, doc.body, ctype, (("X-Doc-Name", urllib.parse.quote(doc.name)),))
			return
		self._send_bytes(404, b"not found", "text/plain; charset=utf-8")

	def do_POST(self):
		srv = self._server
		if self.path.split("?", 1)[0] != "/import":
			self._send_bytes(404, b"not found", "text/plain; charset=utf-8")
			return
		length = int(self.headers.get("Content-Length") or 0)
		if length <= 0:
			self._send_bytes(400, b"empty upload", "text/plain; charset=utf-8")
			return
		body = self.rfile.read(length)
		name = urllib.parse.unquote(self.headers.get("X-Filename") or "imported.txt")
		text = body.decode("utf-8", errors="replace")
		srv.counter += 1
		doc_id = "doc%d" % srv.counter
		doc = _Doc(name or "imported.txt", body, _looks_like_html(name, text))
		srv.docs[doc_id] = doc
		_persist_doc(doc_id, doc)
		payload = ('{"id": "%s"}' % doc_id).encode("utf-8")
		self._send_bytes(200, payload, "application/json; charset=utf-8")

	def log_message(self, format, *args):
		pass


def main(argv=None):
	parser = argparse.ArgumentParser(
		prog="htmlviewer",
		description="View files as interactive, scrollable web pages (HTML files render as-is).",
	)
	parser.add_argument("file", nargs="?", help="path to a file to open on start (optional)")
	parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
	parser.add_argument("--port", type=int, default=8000, help="port to serve on (default: 8000)")
	parser.add_argument("--no-browser", action="store_true", help="do not open a browser automatically")
	args = parser.parse_args(argv)

	app_file = pathlib.Path(__file__).with_name("viewer.html")
	if not app_file.is_file():
		parser.error("missing viewer.html (must sit next to htmlviewer.py)")

	server = _ViewerHTTPServer((args.host, args.port), _ViewerHandler)
	server.app_html = app_file.read_bytes()
	server.docs, server.counter = _load_persisted_docs()

	initial = None
	if args.file:
		path = pathlib.Path(args.file)
		if not path.is_file():
			parser.error(f"no such file: {path}")
		try:
			content = path.read_bytes()
		except OSError as error:
			parser.error(str(error))
		text = content.decode("utf-8", errors="replace")
		server.counter += 1
		initial = "doc%d" % server.counter
		doc = _Doc(path.name, content, _looks_like_html(path.name, text))
		server.docs[initial] = doc
		_persist_doc(initial, doc)

	server.daemon_threads = True

	query = "?id=" + initial if initial else ""
	url = f"http://127.0.0.1:{server.server_address[1]}/{query}"
	print(f"htmlviewer: serving on {url}   (Ctrl+C to stop)")
	print("  import or drop a file in the browser to make it an interactive page")

	if not args.no_browser:
		def _open():
			time.sleep(0.4)
			try:
				webbrowser.open(url)
			except webbrowser.Error:
				pass
		threading.Thread(target=_open, daemon=True).start()

	try:
		server.serve_forever()
	except KeyboardInterrupt:
		print()
	finally:
		server.server_close()


if __name__ == "__main__":
	main()