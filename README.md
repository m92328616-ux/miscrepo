# miscrepo

Small personal tools. No dependencies — everything uses the Python 3 standard
library.

## htmlviewer

Turn any file into an interactive, scrollable web page in your browser.

### Activate it

```sh
python3 htmlviewer.py
```

That starts a local server and opens `http://127.0.0.1:8000/` in your browser
automatically. To stop it, press Ctrl+C in the terminal.

Or open a specific file right away:

```sh
python3 htmlviewer.py notes.txt
python3 htmlviewer.py --port 8080 page.html
```

### What to do after it's running

- Click **Import file…**, or just drag and drop a file onto the page.
- **Text files** become a searchable, scrollable page: line numbers, search
  with match count (Enter / Shift+Enter to jump between hits), a **Wrap**
  toggle, and **+ / −** zoom.
- **HTML files** (`.html`, `.htm`, `.xhtml`, or content that starts with
  `<!doctype` / `<html`) render as-is in the page.
- Hit the **✕** button in the toolbar to close the current document and go
  back to the import screen.

### How it stays offline

Imported files are saved to `.htmlviewer_docs/` next to `htmlviewer.py`, so
they survive the server stopping. Start `htmlviewer.py` again and every
previously imported document is restored. The page also keeps an in-browser
cache of everything you opened.

### Options

| Option             | Meaning                           | Default      |
| ------------------ | --------------------------------- | ------------ |
| `file`             | file to open on start (optional)  | —            |
| `--host <address>` | address to bind                   | `127.0.0.1`  |
| `--port <port>`    | port to serve on                  | `8000`       |
| `--no-browser`     | don't open a browser automatically | —           |

## morse

A translated international chat: Tkinter desktop client (`morse/morse.py`),
TCP server + web host (`morse/server.py`). See `morse/README.md` for full
usage.

```sh
python3 morse/morse.py            # desktop client (opens on International Chat)
python3 morse/server.py           # chat + web host on http://0.0.0.0:8766/
```