# miscrepo

A collection of small, independent tools. Nothing here needs anything beyond
the Python 3 standard library in most cases — no package installs required.

```
miscrepo/
├── htmlviewer/        turn any file into an interactive, scrollable web page
├── morse/             a translated international chat (desktop app + web host)
└── README.md          this file
```

## htmlviewer

Turn any file into an interactive, scrollable page in your browser. Import a
file with a button click or drag-and-drop: text files become a searchable,
line-numbered document (search with Enter / Shift+Enter to jump between hits,
wrap toggle, zoom), and HTML files render as-is. Everything stays offline and
is restored from `.htmlviewer_docs/` the next time you start the tool.

Activate it:

```sh
python3 htmlviewer/htmlviewer.py                  # start the app, import in the browser
python3 htmlviewer/htmlviewer.py notes.txt        # open a specific file right away
python3 htmlviewer/htmlviewer.py --port 8080      # pick a different port
```

Your browser opens automatically at `http://127.0.0.1:8000/`. Press Ctrl+C to
stop. See [`htmlviewer/README.md`](htmlviewer/README.md) for the full guide.

## morse

A Morse-code app and an international chat where everyone's messages are
translated into each reader's own display language. Two ways to join a chat:

| Way | How |
| --- | --- |
| Desktop app (pygame) | `cd morse && python3 morse.py` |
| Any browser (no install) | `python3 morse/server.py`, then open `http://<server-ip>:8766` |

Run the chat server from the `morse/` directory:

```sh
cd morse
python3 server.py --host 0.0.0.0 --port 8765 --http-port 8766
```

The desktop app needs `pygame` (and `numpy`/`sounddevice` for Record Mode):
`pip install pygame numpy sounddevice`. The server and web host use the
standard library only. See [`morse/README.md`](morse/README.md) for the full
documentation.

## Requirements

- Python 3.8+ (the tools use the modern `dict[str, T]` syntax).
- htmlviewer: standard library only.
- morse server + web host: standard library only.
- morse desktop app: `pygame` (and `numpy`, `sounddevice` for Record Mode).