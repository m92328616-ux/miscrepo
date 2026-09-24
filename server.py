#!/usr/bin/env python3
"""International Morse chat server — terminal + web.

Run this on a machine reachable from the internet.  It opens two ports:

  * a raw TCP chat port (default 8765) used by the python morse.py app, and
  * an HTTP web port (default 8766) that serves the Morse chat as a web page,
    so ANYONE can join from any browser/mobile with no software installed:

      http://<this-host>:8766

Every user is geolocated by IP (free ip-api.com request, no key) so the
chat can show each person's country next to their name.

The TCP protocol is one JSON object per line:

  client -> server   {"type": "join",  "nick": ..., "lang": ...}
                     {"type": "chat",  "text": ..., "morse": ...}
  server -> client   {"type": "welcome", "id", "country", "countryCode",
                                         "city", "users": [...]}
                     {"type": "chat",  "nick", "country", "countryCode",
                                         "lang", "text", "morse"}
                     {"type": "join" | "leave", "nick", ...}

The web page uses the same message bus:
  POST /join            {nick, lang}          -> welcome JSON incl. "sid"
  GET  /stream?sid=..   Server-Sent Events    -> chat/join/leave events
  POST /send            {sid, text, morse}    -> broadcast a chat message
  POST /disconnect      {sid}                 -> leave the chat immediately
  GET  /translate?text=..&tl=..               -> translated text (Google proxy)

The plain text always travels alongside the optional morse variant so each
receiver can translate it into their own display language; morse-mode
messages simply show the morse code.
"""

import argparse
import json
import queue
import socket
import threading
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GEOLOCATION_FIELDS = "status,country,countryCode,city,query"
GEO_CACHE = {}

_TRANSLATE_CACHE = {}

# The public endpoint rate-limits per client; try several so a blocked
# client (e.g. HTTP 429) can't silently break translation.
_TRANSLATE_CLIENTS = ("dict-chrome-ex", "gtx")


def google_translate(text, target):
	"""Translate *text* to *target* via the public Google endpoint.

	Returns *text* unchanged if the network is unavailable or rate-limited,
	so a dead translate can never break the chat.  Only successes are
	cached, so a failed request gets retried later.
	"""
	if not text or not target:
		return text
	key = (text, target)
	if key in _TRANSLATE_CACHE:
		return _TRANSLATE_CACHE[key]
	for client in _TRANSLATE_CLIENTS:
		query = urllib.parse.urlencode(
			{"client": client, "sl": "auto", "tl": target, "dt": "t", "q": text}
		)
		request = urllib.request.Request(
			"https://translate.googleapis.com/translate_a/single?" + query,
			headers={
				"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
				"Referer": "https://translate.google.com/",
			},
		)
		try:
			with urllib.request.urlopen(request, timeout=6) as response:
				payload = json.loads(response.read().decode("utf-8"))
			joined = "".join(part[0] for part in payload[0] if part and part[0])
			if joined:
				_TRANSLATE_CACHE[key] = joined
				return joined
		except Exception:
			continue
	return text


def lookup_country(ip):
	"""Resolve a client IP to country info, cached per IP."""
	if ip in GEO_CACHE:
		return GEO_CACHE[ip]
	result = {
		"status": "success",
		"country": "Unknown",
		"countryCode": "--",
		"city": "",
	}
	if ip.startswith("::ffff:"):
		ip = ip[7:]
	if ip in ("127.0.0.1", "::1"):
		result["country"] = "Localhost"
		result["countryCode"] = "--"
		result["city"] = "this machine"
		GEO_CACHE[ip] = result
		return result
	try:
		url = f"http://ip-api.com/json/{ip}?fields={GEOLOCATION_FIELDS}&lang=en"
		with urllib.request.urlopen(url, timeout=5) as response:
			data = json.loads(response.read().decode("utf-8"))
		if data.get("status") == "success":
			result = {
				"status": "success",
				"country": data.get("country", "Unknown"),
				"countryCode": data.get("countryCode", "--"),
				"city": data.get("city", ""),
			}
	except Exception:
		pass
	GEO_CACHE[ip] = result
	return result


def _user_dict(client):
	return {
		"nick": client["nick"],
		"country": client["country"],
		"countryCode": client["countryCode"],
		"city": client["city"],
	}


class ChatServer:
	def __init__(self, host, port, http_port):
		self.host = host
		self.port = port
		self.http_port = http_port
		self.clients = {}       # tcp id        -> client dict (with sock)
		self.web_clients = {}   # web session id -> client dict (with queue)
		self.lock = threading.Lock()
		self.next_id = 1

	def snapshot_users(self):
		with self.lock:
			return [_user_dict(client) for client in self.clients.values()] + [
				_user_dict(client) for client in self.web_clients.values()
			]

	def send(self, client_id, payload):
		"""Send one JSON line to a TCP client."""
		data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
		try:
			self.clients[client_id]["sock"].sendall(data)
		except Exception:
			pass

	def send_web(self, session_id, payload):
		"""Push one event onto a web client's SSE queue."""
		client = self.web_clients.get(session_id)
		if client is None:
			return
		stream = client["queue"]
		if stream.qsize() > 300:
			try:
				stream.get_nowait()
			except queue.Empty:
				pass
		try:
			stream.put_nowait(payload)
		except queue.Full:
			pass

	def broadcast(self, payload, exclude_tcp=None, exclude_web=None):
		with self.lock:
			tcp_ids = list(self.clients)
			web_ids = list(self.web_clients)
		for client_id in tcp_ids:
			if client_id != exclude_tcp:
				self.send(client_id, payload)
		for session_id in web_ids:
			if session_id != exclude_web:
				self.send_web(session_id, payload)

	def register_web(self, nick, lang, ip):
		"""Create a web session and return (sid, geo, online_users)."""
		geo = lookup_country(ip)
		session_id = uuid.uuid4().hex[:12]
		with self.lock:
			self.web_clients[session_id] = {
				"queue": queue.Queue(maxsize=512),
				"nick": nick,
				"lang": lang,
				"country": geo.get("country", "Unknown"),
				"countryCode": geo.get("countryCode", "--"),
				"city": geo.get("city", ""),
				"source": "web",
			}
			online = [
				_user_dict(client) for client in self.clients.values()
			] + [
				_user_dict(client) for client in self.web_clients.values()
			]
		return session_id, geo, online

	def remove_web(self, session_id):
		with self.lock:
			rec = self.web_clients.pop(session_id, None)
		if rec is not None:
			self.broadcast({"type": "leave", "nick": rec["nick"]})
			print(f"[-] {rec['nick']} left  (web)  - {len(self.snapshot_users())} online")

	def handle(self, sock, address):
		"""Talk to a single python-client connection until it disconnects."""
		ip = address[0]
		geo = lookup_country(ip)
		with self.lock:
			client_id = self.next_id
			self.next_id += 1

		buffer = b""
		sock.settimeout(0.2)

		def read_line():
			nonlocal buffer
			while b"\n" not in buffer:
				try:
					chunk = sock.recv(4096)
				except socket.timeout:
					continue
				except OSError:
					return None
				if not chunk:
					return None
				buffer += chunk
			line, _, buffer = buffer.partition(b"\n")
			return line.decode("utf-8", "replace")

		joined = False
		nick = "?"
		try:
			first = read_line()
			if not first:
				return
			hello = json.loads(first)
			nick = str(hello.get("nick") or "User")[:24]
			lang = str(hello.get("lang") or "en")[:8] or "en"

			with self.lock:
				self.clients[client_id] = {
					"sock": sock,
					"nick": nick,
					"lang": lang,
					"country": geo.get("country", "Unknown"),
					"countryCode": geo.get("countryCode", "--"),
					"city": geo.get("city", ""),
					"source": "app",
				}
				self.next_id = max(self.next_id, client_id + 1)
				online = [
					_user_dict(client) for client in self.clients.values()
				] + [
					_user_dict(client) for client in self.web_clients.values()
				]
			joined = True

			self.send(client_id, {
				"type": "welcome",
				"id": client_id,
				"country": geo.get("country", "Unknown"),
				"countryCode": geo.get("countryCode", "--"),
				"city": geo.get("city", ""),
				"users": online,
			})
			self.broadcast({
				"type": "join",
				"nick": nick,
				"country": geo.get("country", "Unknown"),
				"countryCode": geo.get("countryCode", "--"),
				"city": geo.get("city", ""),
			}, exclude_tcp=client_id)
			print(f"[+] {nick}  ({geo.get('countryCode', '--')} {geo.get('country', '')})  - {len(online)} online")

			while True:
				line = read_line()
				if line is None:
					break
				try:
					payload = json.loads(line)
				except ValueError:
					continue
				kind = payload.get("type")
				if kind == "chat":
					text = str(payload.get("text") or "")[:400]
					morse = str(payload.get("morse") or "")[:1200] or None
					with self.lock:
						client = self.clients.get(client_id)
						if client is None:
							break
						country = client["country"]
						country_code = client["countryCode"]
						lang = client["lang"]
					self.broadcast({
						"type": "chat",
						"nick": nick,
						"country": country,
						"countryCode": country_code,
						"lang": lang,
						"text": text,
						"morse": morse,
					}, exclude_tcp=client_id)
					print(f"[{nick}|{country_code}] {morse or text}")
				elif kind == "ping":
					self.send(client_id, {"type": "pong"})
		except (ValueError, json.JSONDecodeError):
			pass
		except Exception as exc:
			print(f"[!] error from {ip}: {exc}")
		finally:
			if joined:
				with self.lock:
					self.clients.pop(client_id, None)
				self.broadcast({"type": "leave", "nick": nick})
				print(f"[-] {nick} left  - {len(self.snapshot_users())} online")
			try:
				sock.close()
			except OSError:
				pass

	def run(self):
		httpd = ChatHTTPServer((self.host, self.http_port), WebChatHandler)
		httpd.chatserver = self
		httpd.daemon_threads = True
		web_thread = threading.Thread(
			target=httpd.serve_forever, daemon=True, name="web-http"
		)
		web_thread.start()

		server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		server.bind((self.host, self.port))
		server.listen(50)
		print(f"WEB chat:      http://{self.host or '<your-ip>'}:{self.http_port}   (any browser, no install)")
		print(f"Terminal chat: {self.host or '<your-ip>'}:{self.port}   (python3 morse.py --connect)")
		print("People can join the web chat from a phone/PC with just a browser.")
		print()
		try:
			while True:
				sock, address = server.accept()
				threading.Thread(target=self.handle, args=(sock, address), daemon=True).start()
		finally:
			httpd.shutdown()


class ChatHTTPServer(ThreadingHTTPServer):
	chatserver: "ChatServer"


class WebChatHandler(BaseHTTPRequestHandler):
	protocol_version = "HTTP/1.0"

	def log_message(self, format, *args):
		pass

	@property
	def chatserver(self):
		if isinstance(self.server, ChatHTTPServer):
			return self.server.chatserver
		raise RuntimeError("no chat server attached")

	def _json(self, obj, status=200):
		data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(data)))
		self.end_headers()
		self.wfile.write(data)

	def _page(self, body, status=200, content_type="text/html; charset=utf-8"):
		data = body.encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(len(data)))
		self.end_headers()
		self.wfile.write(data)

	def _read_json(self):
		length = int(self.headers.get("Content-Length") or 0)
		raw = self.rfile.read(length) if length else b"{}"
		try:
			return json.loads(raw.decode("utf-8"))
		except ValueError:
			return {}

	def do_GET(self):
		parsed = urllib.parse.urlparse(self.path)
		path = parsed.path
		if path in ("/", "/index.html"):
			self._page(WEB_PAGE)
		elif path == "/stream":
			self._stream(parsed)
		elif path == "/translate":
			self._translate(parsed)
		else:
			self._json({"error": "not found"}, 404)

	def do_POST(self):
		path = urllib.parse.urlparse(self.path).path
		if path == "/join":
			self._join()
		elif path == "/send":
			self._send()
		elif path == "/disconnect":
			self._disconnect()
		else:
			self._json({"error": "not found"}, 404)

	def _join(self):
		data = self._read_json()
		nick = str(data.get("nick") or "Guest")[:24] or "Guest"
		lang = str(data.get("lang") or "en")[:8] or "en"
		session_id, geo, online = self.chatserver.register_web(
			nick, lang, self.client_address[0]
		)
		self.chatserver.broadcast({
			"type": "join",
			"nick": nick,
			"country": geo.get("country", "Unknown"),
			"countryCode": geo.get("countryCode", "--"),
			"city": geo.get("city", ""),
		}, exclude_web=session_id)
		print(f"[+] {nick}  ({geo.get('countryCode', '--')} {geo.get('country', '')})  - {len(online)} online  (web)")
		self._json({
			"type": "welcome",
			"sid": session_id,
			"country": geo.get("country", "Unknown"),
			"countryCode": geo.get("countryCode", "--"),
			"city": geo.get("city", ""),
			"users": online,
		})

	def _send(self):
		data = self._read_json()
		session_id = str(data.get("sid") or "")
		chatserver = self.chatserver
		with chatserver.lock:
			client = chatserver.web_clients.get(session_id)
		if client is None:
			self._json({"error": "unknown session"}, 400)
			return
		text = str(data.get("text") or "")[:400]
		morse = str(data.get("morse") or "")[:1200] or None
		chatserver.broadcast({
			"type": "chat",
			"nick": client["nick"],
			"country": client["country"],
			"countryCode": client["countryCode"],
			"lang": client["lang"],
			"text": text,
			"morse": morse,
		}, exclude_web=session_id)
		print(f"[{client['nick']}|{client['countryCode']}] {morse or text}")
		self._json({"ok": True})

	def _disconnect(self):
		data = self._read_json()
		session_id = str(data.get("sid") or "")
		if not session_id:
			self._json({"error": "missing sid"}, 400)
			return
		self.chatserver.remove_web(session_id)
		self._json({"ok": True})

	def _translate(self, parsed):
		params = urllib.parse.parse_qs(parsed.query)
		text = (params.get("text") or [""])[0][:400]
		target = (params.get("tl") or ["en"])[0][:8] or "en"
		self._json({"translated": google_translate(text, target)})

	def _stream(self, parsed):
		params = urllib.parse.parse_qs(parsed.query)
		session_id = (params.get("sid") or [""])[0]
		chatserver = self.chatserver
		client = chatserver.web_clients.get(session_id)
		if client is None:
			self._json({"error": "unknown session"}, 400)
			return
		self.send_response(200)
		self.send_header("Content-Type", "text/event-stream")
		self.send_header("Cache-Control", "no-cache")
		self.send_header("X-Accel-Buffering", "no")
		self.end_headers()
		try:
			stream = client["queue"]
			while True:
				try:
					event = stream.get(timeout=12)
				except queue.Empty:
					try:
						self.wfile.write(b": keep-alive\n\n")
						self.wfile.flush()
					except OSError:
						break
					continue
				payload = json.dumps(event, ensure_ascii=False)
				try:
					self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
					self.wfile.flush()
				except OSError:
					break
		finally:
			chatserver.remove_web(session_id)


WEB_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Morse Machine — International Chat</title>
<style>
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    background: #0c121b; color: #ebf0f5;
    font-family: "DejaVu Sans", system-ui, sans-serif;
    display: flex; flex-direction: column; height: 100vh;
  }
  header {
    background: #0f1e28; padding: 12px 18px; display: flex;
    align-items: baseline; gap: 14px; flex-wrap: wrap; border-bottom: 1px solid #16242e;
  }
  h1 { font-size: 20px; margin: 0; letter-spacing: 2px; }
  .sub { color: #4dc9b0; font-size: 13px; }
  #status { margin-left: auto; font-weight: bold; color: #9cabbb; }
  #status.ok { color: #4dc9b0; }
  #status.bad { color: #f2ba49; }
  .toolbar {
    background: #18222f; padding: 10px 18px; display: flex; gap: 8px;
    flex-wrap: wrap; align-items: center;
  }
  .toolbar input[type=text], .toolbar select {
    background: #1f2c3b; color: #ebf0f5; border: 1px solid #2a3949;
    border-radius: 6px; padding: 8px 10px; font-size: 14px;
  }
  button {
    background: #1f2c3b; color: #ebf0f5; border: 1px solid #2a3949;
    border-radius: 6px; padding: 8px 12px; font-size: 14px; cursor: pointer;
  }
  button:hover { border-color: #4dc9b0; }
  button.on { background: #2d585b; border-color: #4dc9b0; color: #4dc9b0; }
  #users { color: #9cabbb; font-size: 12px; padding: 6px 18px; word-break: break-word; }
  main { flex: 1; overflow-y: auto; padding: 10px 18px; }
  .msg { margin-bottom: 8px; }
  .head { color: #4dc9b0; font-size: 13px; font-weight: bold; }
  .head .country { color: #9cabbb; font-weight: normal; }
  .body { color: #ff6; white-space: pre-wrap; word-break: break-word; }
  .body.text { color: #ebf0f5; }
  .note { color: #9cabbb; font-size: 13px; margin-top: 2px; }
  .sys { color: #9cabbb; font-size: 13px; margin: 4px 0; }
  footer {
    background: #18222f; padding: 10px 18px; display: flex; gap: 8px;
    align-items: center; border-top: 1px solid #16242e;
  }
  footer .prefix { color: #4dc9b0; font-weight: bold; }
  footer .prefix.morse { color: #f2ba49; }
  footer input {
    flex: 1; background: #0c121b; color: #ebf0f5; border: 1px solid #2a3949;
    border-radius: 6px; padding: 10px; font-size: 16px;
  }
  #live {
    background: #0f1e28; border-top: 1px solid #16242e; padding: 8px 18px;
    font-family: "DejaVu Sans Mono", monospace; font-size: 13px; color: #4dc9b0;
    white-space: pre-wrap; word-break: break-all;
  }
  #live .dec { color: #9cabbb; }
  #ref {
    background: #18222f; border: 1px solid #2a3949; border-radius: 8px;
    margin: 10px 18px 2px; padding: 12px; display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px;
    font-family: "DejaVu Sans Mono", monospace; font-size: 13px;
    position: sticky; bottom: 0; max-height: 40vh; overflow-y: auto;
  }
  #ref span { display: inline-block; }
</style>
</head>
<body>
<header>
  <h1>MORSE MACHINE</h1>
  <div class="sub">International chat</div>
  <div id="status">disconnected</div>
</header>

<div class="toolbar">
  <input id="nick" type="text" placeholder="Your name" maxlength="24">
  <select id="lang"></select>
  <select id="mode">
    <option value="normal">CHAT: Text</option>
    <option value="m2w">CHAT: Morse to Word</option>
    <option value="w2m">CHAT: Words to Morse</option>
  </select>
  <button id="refBtn">REFERENCE</button>
  <button id="connectBtn">CONNECT</button>
</div>

<div id="users"></div>
<main id="log"></main>

<div id="ref" style="display:none"></div>

<div id="live" style="display:none"></div>

<footer>
  <span class="prefix" id="prefix">TEXT:</span>
  <input id="input" type="text" placeholder="Type a message and press Enter…" maxlength="400">
  <button id="sendBtn">Send</button>
</footer>

<script>
"use strict";

var MORSE = {
  A:".-", B:"-...", C:"-.-.", D:"-..", E:".", F:"..-.", G:"--.", H:"....", I:"..", J:".---",
  K:"-.-", L:".-..", M:"--", N:"-.", O:"---", P:".--.", Q:"--.-", R:".-.", S:"...", T:"-",
  U:"..-", V:"...-", W:".--", X:"-..-", Y:"-.--", Z:"--..",
  "0":"-----","1":".----","2":"..---","3":"...--","4":"....-","5":".....","6":"-....","7":"--...","8":"---..","9":"----."
};

var LANGS = [
  ["en","English"],["es","Spanish"],["pt","Portuguese"],["fr","French"],["de","German"],
  ["it","Italian"],["nl","Dutch"],["pl","Polish"],["ru","Russian"],["uk","Ukrainian"],
  ["sv","Swedish"],["tr","Turkish"],["ar","Arabic"],["hi","Hindi"],["zh-CN","Chinese"],
  ["ja","Japanese"],["ko","Korean"]
];

var state = { sid: null, nick: "", lang: "en", mode: "normal", morseBuf: "", users: [], es: null };
var tcache = {};

var $ = function(id) { return document.getElementById(id); };
var logEl = $("log"), usersEl = $("users"), statusEl = $("status"),
    nickEl = $("nick"), langEl = $("lang"), modeEl = $("mode"),
    refBtn = $("refBtn"), connectBtn = $("connectBtn"), inputEl = $("input"),
    sendBtn = $("sendBtn"), refEl = $("ref"), prefixEl = $("prefix"), liveEl = $("live");

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = cls || "";
}

function encodeTextToMorse(text) {
  var words = text.toUpperCase().split(/\s+/).filter(Boolean);
  var out = [];
  for (var i = 0; i < words.length; i++) {
    var clean = "";
    var chars = words[i].split("");
    for (var j = 0; j < chars.length; j++) {
      if (MORSE.hasOwnProperty(chars[j])) {
        clean += (clean ? " " : "") + MORSE[chars[j]];
      }
    }
    if (clean) out.push(clean);
  }
  return out.join(" / ");
}

var MORSE_REV = {};
(function() {
  var keys = Object.keys(MORSE);
  for (var i = 0; i < keys.length; i++) MORSE_REV[MORSE[keys[i]]] = keys[i];
})();

function decodeMorse(buf) {
  if (!buf) return "";
  return buf.trim().split(" / ").map(function(w) {
    var letters = w.split(" ").filter(Boolean);
    return letters.map(function(l) {
      return MORSE_REV.hasOwnProperty(l) ? MORSE_REV[l] : "?";
    }).join("");
  }).join(" ");
}

function morseSpaceKey() {
  if (!state.morseBuf || state.morseBuf.trim().endsWith("/")) return;
  if (state.morseBuf.endsWith(" ")) state.morseBuf = state.morseBuf.trim() + " / ";
  else state.morseBuf += " ";
}

function morseSlashKey() {
  if (!state.morseBuf || state.morseBuf.trim().endsWith("/")) return;
  state.morseBuf = state.morseBuf.trim() + " / ";
}

function sameLang(a, b) {
  return (a || "").split("-")[0].toLowerCase() === (b || "").split("-")[0].toLowerCase();
}

function translateText(text, target) {
  if (!text || !target) return Promise.resolve(text);
  var key = target + ":" + text;
  if (tcache[key] !== undefined) return Promise.resolve(tcache[key]);
  return fetch("/translate?text=" + encodeURIComponent(text) + "&tl=" + encodeURIComponent(target))
    .then(function(r) { return r.json(); })
    .then(function(d) { var v = (d && d.translated) || text; tcache[key] = v; return v; })
    .catch(function() { return text; });
}

function trimLog() {
  while (logEl.childElementCount > 300) logEl.removeChild(logEl.firstChild);
}

function addSys(text) {
  var el = document.createElement("div");
  el.className = "sys";
  el.textContent = text;
  logEl.appendChild(el);
  trimLog();
  logEl.scrollTop = logEl.scrollHeight;
}

function addChat(m) {
  var nick = m.nick || "?";
  var country = m.country || m.countryCode || "";
  var isMorse = !!(m.morse);
  var entry = document.createElement("div");
  entry.className = "msg";

  var head = document.createElement("div");
  head.className = "head";
  head.textContent = nick;
  if (country) {
    var cc = document.createElement("span");
    cc.className = "country";
    cc.textContent = "  [" + country + "]";
    head.appendChild(cc);
  }

  var body = document.createElement("div");
  body.className = "body " + (isMorse ? "morse" : "text");
  body.textContent = isMorse ? m.morse : (m.text || "");
  entry.appendChild(head);
  entry.appendChild(body);
  logEl.appendChild(entry);

  if (isMorse && m.text) {
    var note = document.createElement("div");
    note.className = "note";
    note.textContent = "...";
    entry.appendChild(note);
    translateText(m.text, state.lang).then(function(t) { note.textContent = "-> " + t; });
  } else if (!isMorse && m.text && (m.own || (m.lang && !sameLang(m.lang, state.lang)))) {
    translateText(m.text, state.lang).then(function(t) { body.textContent = t; });
  }

  trimLog();
  logEl.scrollTop = logEl.scrollHeight;
}

function renderUsers() {
  var names = state.users.map(function(u) { return u.nick; });
  usersEl.textContent = state.users.length + " online:  " + names.join(",  ");
}

function join() {
  if (state.sid) return;
  var nick = (nickEl.value.trim() || "Guest").slice(0, 24);
  state.nick = nick;
  state.lang = langEl.value;
  fetch("/join", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nick: nick, lang: state.lang })
  }).then(function(r) { return r.json(); }).then(function(d) {
    state.sid = d.sid;
    state.users = d.users || [];
    renderUsers();
    var place = d.country || d.countryCode || "?";
    setStatus("CONNECTED - you are " + nick + " - " + place, "ok");
    addSys("Connected as " + nick + " from " + place);
    openStream();
    connectBtn.textContent = "DISCONNECT";
    connectBtn.classList.add("on");
  }).catch(function() {
    setStatus("CONNECT FAILED - retry", "bad");
    connectBtn.textContent = "CONNECT";
    connectBtn.classList.remove("on");
  });
}

function disconnect() {
  if (state.sid) {
    fetch("/disconnect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sid: state.sid })
    }).catch(function() {});
  }
  if (state.es) { state.es.close(); state.es = null; }
  state.sid = null;
  state.users = [];
  renderUsers();
  setStatus("disconnected");
  connectBtn.textContent = "CONNECT";
  connectBtn.classList.remove("on");
}

function openStream() {
  if (state.es) state.es.close();
  state.es = new EventSource("/stream?sid=" + encodeURIComponent(state.sid));
  state.es.onmessage = function(ev) {
    var m;
    try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === "chat") addChat(m);
    else if (m.type === "join") {
      addSys("+ " + (m.nick || "?") + " joined from " + (m.country || "?"));
      state.users.push({ nick: m.nick, country: m.country || "" });
      renderUsers();
    } else if (m.type === "leave") {
      addSys("- " + (m.nick || "?") + " left");
      state.users = state.users.filter(function(u) { return u.nick !== m.nick; });
      renderUsers();
    }
  };
  state.es.onerror = function() {
    setStatus("CONNECTION LOST - click CONNECT to retry", "bad");
    if (state.es) { state.es.close(); state.es = null; }
    state.sid = null;
    connectBtn.textContent = "CONNECT";
    connectBtn.classList.remove("on");
  };
}

function send() {
  if (!state.sid) { addSys("Connect first."); return; }
  var text = "", morse = "";
  if (state.mode === "m2w") {
    morse = state.morseBuf.trim();
    if (!morse) return;
    text = decodeMorse(morse) || morse;
  } else {
    text = inputEl.value.trim();
    if (!text) return;
    if (state.mode === "w2m") morse = encodeTextToMorse(text);
  }
  fetch("/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sid: state.sid, text: text, morse: morse })
  }).catch(function() {});
  addChat({ nick: state.nick, country: "", lang: state.lang, text: text, morse: morse, own: true });
  inputEl.value = "";
  state.morseBuf = "";
  renderMorse();
  if (state.mode !== "m2w") inputEl.focus();
}

function applyMode() {
  state.mode = modeEl.value;
  var m2w = state.mode === "m2w";
  inputEl.style.display = m2w ? "none" : "";
  if (m2w) prefixEl.textContent = "MORSE>WORD:";
  else if (state.mode === "w2m") prefixEl.textContent = "WORDS>MORSE:";
  else prefixEl.textContent = "TEXT:";
  prefixEl.classList.toggle("morse", state.mode !== "normal");
  if (m2w && document.activeElement && document.activeElement.blur) document.activeElement.blur();
  renderMorse();
}

function renderMorse() {
  if (state.mode === "m2w") {
    liveEl.style.display = "block";
    liveEl.textContent = "";
    var mor = document.createElement("span");
    mor.textContent = state.morseBuf || "press  .  -  space  /  then Enter to send";
    liveEl.appendChild(mor);
    if (state.morseBuf) {
      var dec = document.createElement("span");
      dec.className = "dec";
      dec.textContent = "   ->   " + (decodeMorse(state.morseBuf) || "?");
      liveEl.appendChild(dec);
    }
  } else if (state.mode === "w2m") {
    var t = inputEl.value.trim();
    liveEl.style.display = t ? "block" : "none";
    liveEl.textContent = t ? encodeTextToMorse(t) : "";
  } else {
    liveEl.style.display = "none";
  }
}

function morseKey(e) {
  if (state.mode !== "m2w") return;
  if (e.key === ".") state.morseBuf += ".";
  else if (e.key === "-") state.morseBuf += "-";
  else if (e.key === " ") morseSpaceKey();
  else if (e.key === "/") morseSlashKey();
  else if (e.key === "Enter") send();
  else if (e.key === "Backspace") state.morseBuf = state.morseBuf.slice(0, -1);
  else return;
  e.preventDefault();
  renderMorse();
}

function buildRef() {
  var keys = Object.keys(MORSE);
  refEl.innerHTML = "";
  for (var i = 0; i < keys.length; i++) {
    var sp = document.createElement("span");
    sp.textContent = keys[i] + "  " + MORSE[keys[i]];
    refEl.appendChild(sp);
  }
}

nickEl.value = localStorage.getItem("mm_nick") || (new URLSearchParams(location.search).get("nick") || "");
langEl.innerHTML = "";
for (var li = 0; li < LANGS.length; li++) {
  var opt = document.createElement("option");
  opt.value = LANGS[li][0];
  opt.textContent = LANGS[li][1];
  langEl.appendChild(opt);
}
langEl.value = localStorage.getItem("mm_lang") || "en";

langEl.addEventListener("change", function() {
  state.lang = langEl.value;
  localStorage.setItem("mm_lang", state.lang);
});
nickEl.addEventListener("change", function() {
  localStorage.setItem("mm_nick", nickEl.value);
});
modeEl.addEventListener("change", applyMode);
refBtn.addEventListener("click", function() {
  if (refEl.style.display === "none") {
    buildRef();
    refEl.style.display = "grid";
  } else {
    refEl.style.display = "none";
  }
});
connectBtn.addEventListener("click", function() {
  if (state.sid) disconnect();
  else join();
});
sendBtn.addEventListener("click", send);
inputEl.addEventListener("keydown", function(e) {
  if (e.key === "Enter") send();
  if (e.key === "Tab") {
    e.preventDefault();
    if (refEl.style.display === "none") { buildRef(); refEl.style.display = "grid"; }
    else refEl.style.display = "none";
  }
});
inputEl.addEventListener("input", renderMorse);
window.addEventListener("keydown", morseKey);

applyMode();
</script>
</body>
</html>"""


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Morse international chat server (terminal + web)")
	parser.add_argument("--host", default="0.0.0.0", help="address to bind (default 0.0.0.0)")
	parser.add_argument("--port", type=int, default=8765, help="TCP chat port (default 8765)")
	parser.add_argument("--http-port", type=int, default=8766, help="web port (default 8766)")
	args = parser.parse_args()
	ChatServer(args.host, args.port, args.http_port).run()