"""Regression tests for the web host's chat translation.

The web host page must translate every chat message into the viewer's chosen
display language, no matter what language the sender picked in their own
toolbar (the sender's ``lang`` field is a UI preference, not the message's
language).  It must also re-translate every already-visible message when the
display language changes.

These tests run the real <script> block served by ``morse.server`` in Node
against a mock DOM and a canned /translate backend.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


_SERVER_PATH = pathlib.Path(__file__).resolve().parent / "server.py"


def _web_script():
    source = _SERVER_PATH.read_text(encoding="utf-8")
    match = re.search(r"<script>(.*)</script>", source, re.S)
    assert match, "no <script> block found in WEB_PAGE"
    return match.group(1)


_HARNESS_BASE = r"""
const fs = require("fs");
const vm = require("vm");

class Element {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.parent = null; this.style = {};
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
    this.dataset = {}; this._text = ""; this.value = "";
  }
  get textContent() { return this._text; }
  set textContent(v) { this._text = String(v); }
  get childElementCount() { return this.children.length; }
  get firstChild() { return this.children[0] || null; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; }
  remove() { if (this.parent) this.parent.removeChild(this); }
  addEventListener(t, f) { (this._listeners = this._listeners || {})[t] = f; }
}

const logEl = new Element("div");
const ids = { log: logEl, users: new Element("div"), status: new Element("div"),
  nick: new Element("input"), lang: new Element("select"), mode: new Element("select"),
  refBtn: new Element("button"), connectBtn: new Element("button"),
  input: new Element("input"), sendBtn: new Element("button"), ref: new Element("div"),
  prefix: new Element("span"), live: new Element("span") };
const document = {
  getElementById(id) { return ids[id] || null; },
  createElement(tag) { return new Element(tag); },
};

const canned = {
  "что такое привет?":   { ru: "Привет это привет", en: "what is hello" },
  "что такое снеговик?": { ru: "Снеговик это снеговик", en: "what is a snowman" },
  "Hola":                { ru: "Привет", en: "Hello" },
};
global.fetch = (url) => {
  const query = new URLSearchParams(url.split("?")[1] || "");
  const text = query.get("text") || "";
  const target = query.get("tl") || "";
  const box = canned[text];
  const value = (box && box[target]) || text;
  return Promise.resolve({ json: () => Promise.resolve({ translated: value }) });
};
global.window = global;
global.location = { search: "" };
global.localStorage = { _d: {}, getItem(k) { return this._d[k] ?? null; }, setItem(k, v) { this._d[k] = String(v); } };
global.EventSource = function () {};
global.document = document;
global.addEventListener = () => {};

vm.runInThisContext(fs.readFileSync(process.argv[2], "utf8"));

function bodies() {
  const rows = [];
  for (const el of logEl.children) {
    const body = el.children.find(c => c.className && String(c.className).startsWith("body"));
    const note = el.children.find(c => c.className === "note");
    rows.push({ body: body ? String(body._text) : null, note: note ? String(note._text) : null });
  }
  return rows;
}
"""

_HARNESS_SAME_LANG = _HARNESS_BASE + r"""
// Viewer display language is English.  A sender whose OWN toolbar is also
// English sends a Spanish word: it must still be translated for the viewer.
state.lang = "en"; langEl.value = "en";
addChat({ nick: "Juan", lang: "en", text: "Hola", morse: null });
setTimeout(() => {
  const rows = bodies();
  console.log("RESULT " + JSON.stringify(rows));
  process.exit(0);
}, 30);
"""

_HARNESS_RETRANSLATE = _HARNESS_BASE + r"""
// Two plain messages plus one morse message arrive while the host shows Russian.
state.lang = "ru"; langEl.value = "ru";
addChat({ nick: "A", lang: "de", text: "что такое привет?", morse: null });
addChat({ nick: "B", lang: "de", text: "что такое снеговик?", morse: null });
addChat({ nick: "C", lang: "de", text: "что такое снеговик?", morse: ".... . .-.. .-.. ---" });

setTimeout(() => {
  // Host switches the display language to English: retranslateAll must update
  // EVERY visible message with its own new translation.
  state.lang = "en"; langEl.value = "en"; langEl._listeners.change();
  setTimeout(() => {
    console.log("RESULT " + JSON.stringify(bodies()));
    process.exit(0);
  }, 30);
}, 30);
"""


class _NodeCase(unittest.TestCase):
    GETATTR_PATTERN = re.compile(r"test_(\w+)")

    def run_scenario(self, harness):
        if not shutil.which("node"):
            self.skipTest("node is required to run the web page script")
        with tempfile.TemporaryDirectory() as tmp:
            script_path = os.path.join(tmp, "webscript.js")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(_web_script())
            harness_path = os.path.join(tmp, "harness.js")
            with open(harness_path, "w", encoding="utf-8") as handle:
                handle.write(textwrap.dedent(harness))
            proc = subprocess.run(
                ["node", harness_path, script_path],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            marker = "RESULT "
            line = next((ln for ln in proc.stdout.splitlines() if ln.startswith(marker)), None)
            if line is None:
                self.fail("node harness printed no RESULT line:\n" + proc.stdout)
            return json.loads(line[len(marker):])


@unittest.skipUnless(shutil.which("node"), "node is required to run the web page script")
class WebHostSameLangTranslationTests(_NodeCase):
    def test_message_in_sender_language_that_matches_viewer_is_still_translated(self):
        rows = self.run_scenario(_HARNESS_SAME_LANG)
        # "Hola" matches the viewer's toolbar language (en) but is Spanish:
        # it must still be translated and keep the original as a grey sub-line.
        self.assertEqual(rows[0]["body"], "Hello")
        self.assertEqual(rows[0]["note"], None)


@unittest.skipUnless(shutil.which("node"), "node is required to run the web page script")
class WebHostRetranslateTests(_NodeCase):
    def test_retranslate_all_updates_every_message_after_language_switch(self):
        rows = self.run_scenario(_HARNESS_RETRANSLATE)
        # Both plain messages must carry their own English translation, and
        # the morse message keeps its code with its own translated note.
        self.assertEqual(rows[0]["body"], "what is hello")
        self.assertEqual(rows[1]["body"], "what is a snowman")
        self.assertEqual(rows[2]["body"], ".... . .-.. .-.. ---")
        self.assertEqual(rows[2]["note"], "-> what is a snowman")


if __name__ == "__main__":
    unittest.main()