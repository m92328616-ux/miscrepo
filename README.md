# miscrepo

A collection of miscellaneous projects. The current project is a **Morse machine** (pygame desktop app plus a terminal chat server that connects Morse users around the world).

## Morse Machine (`morse.py`)

A pygame desktop app for sending and decoding Morse code. Launch it with:

```bash
python3 morse.py
```

### Input modes

Pick a mode from the `INPUT MODE` dropdown (or press `Up` / `Down` to cycle):

| Mode | What it does |
| --- | --- |
| **Duration Mode** | Tap `SPACE` briefly (under ~180ms) for a dot, hold longer for a dash. Auto-commits letters/words based on pause length. |
| **Dot Stream Mode** | Tap `SPACE` for a dash, hold it to stream repeating dots. |
| **Keyboard Buttons** | Press `.` for a dot, `-` for a dash. |
| **Translator Mode** | Type a word or phrase; the app translates it live into your chosen display language and shows the Morse output with a `SOUND` button to hear it (adjustable playback speed). Use the `LANG` dropdown to pick the target language — the selected language is always the translation target, the source language is auto-detected, and changing the language instantly re-translates the current text. |
| **Record Mode** | Point your mic at Morse beeps. Uses FFT tonality analysis to ignore human speech and only decode pure tones. `M` (or the button) toggles slow-motion; `Enter` forces a letter. |
| **International Chat** | Connect to a shared chat server to talk with Morse users around the world (see below). |

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Space` | Key down detection (non-chat modes) |
| `.` / `-` | Dot / dash in Keyboard Buttons mode |
| `Enter` | Force a letter / send a chat message |
| `Backspace` | Clear the current input |
| `Delete` | Delete last character |
| `Tab` | Show the Morse code cheat-sheet window |
| `Esc` | Quit |

### Word prediction

Record Mode, Keyboard Buttons, and the other sender modes predict the word
being formed as you send. Predictions are computed from the real letter
sequence being typed, so a Morse run never cuts across a letter boundary
(a three-dot run suggests `S`/`V`/`H` words, never `IS`, which starts with
`..`). The letters already committed in the current word are taken into
account — after sending `H` then `E`, tapping the start of `L` predicts
`HELP` / `HELLO` instead of unrelated words. Completed letters are
prioritised over partial guesses, and when several words fit, the most
common ones are listed first. Finished numbers (e.g. `.....` = 5) fall back
to letter prediction instead of odd word guesses.

The prediction logic lives in `morse.py`:
`predict_letters()` (characters matching a partial run), `_predict_words()`
(full word candidates given the current run + committed letters) and
`decode_obvious()` (best decoding of a run). There is a unit-test suite:

```bash
python3 -m unittest test_morse -v
```

## International Chat

The International Chat mode lets people across the world connect to a central server chat in three ways: plain text, **manual Morse** (tap `.`/`-`/`space` and it decodes to words as you type), or **words auto-converted to Morse**. Every user's country is shown next to their name.

Anyone can join two ways:

- **From a browser** — no software to install at all (works on phones too), or
- **From the Morse machine** (`morse.py`), for the desktop experience with sound.

### 1. Run the server (one host)

Start the chat server on a machine reachable from the internet (open TCP port 8765 **and** HTTP port 8766 on its firewall):

```bash
python3 server.py --host 0.0.0.0 --port 8765 --http-port 8766
```

- The server **geolocates every client by IP** with the free [ip-api.com](https://ip-api.com) service (no API key needed).
- Every connection, join/leave and chat message is logged to the terminal.
- Web and desktop (Morse machine) users all share the same chat and see each other.

### 2. Connect from a browser — no install

Just share this address with anyone; they open it in any browser on any device:

```
http://<server-ip>:8766
```

The page gives them everything the desktop app's chat has — nick, display language, the Morse reference sheet, live online list — with zero install. A friend on a phone can join with zero setup.

### 3. Connect from the Morse machine

```bash
python3 morse.py --connect --server <server-ip> --nick <name> [--lang <code>]
```

Without `--connect`, pick **International Chat** from the input-mode dropdown instead.

Full command line options:

| Flag | Description | Default |
| --- | --- | --- |
| `--server <host>` | Chat server host to connect to | `127.0.0.1` |
| `--port <port>` | Chat server port | `8765` |
| `--nick <name>` | Your display name in the chat | OS username |
| `--lang <code>` | Your chat display language (e.g. `en`, `pt`, `es`, `fr`, `zh-CN`) | `en` |
| `--connect` | Open directly on International Chat mode | off |

### Chat modes

Three input modes (choose from the **CHAT MODE** button on the desktop, or the **CHAT** dropdown on the web page):

| Mode | What it does |
| --- | --- |
| **Normal** (`TEXT`) | Type your message plainly; it is sent as text. |
| **Morse to Word** (`MORSE>WORD`) | The text bar disappears — press `.` for a dot and `-` for a dash, `space` closes a letter, `space` again (or `/`) starts a new word. Your Morse is decoded to words live as you type, and sent as Morse with the decoded words, so everyone gets both. |
| **Words to Morse** (`WORDS>MORSE`) | Type words and they are sent as their Morse translation too (e.g. *hello world* → `.... . .-.. .-.. --- / .-- --- .-. .-.. -..`), still translated into each reader's language. |

### How the chat works

- **Send text** — press `Enter` to send the current input.
- **Morse to Word** — manual Morse entry; *hello* becomes `.... . .-.. .-.. ---` as you tap, and `Enter` sends it with the decoded word `HELLO`.
- **Display language** — open the **LANG** dropdown and pick your language. Incoming messages are automatically translated into that language using the free Google Translate endpoint, in a background thread so the UI never freezes. If translation is unavailable the original text is shown.
- **Country** — each message shows the sender's country, resolved from their IP by the server.
- The **CONNECT / DISCONNECT** button controls the connection; the header shows your status and the current online users.

### Web interface

Web clients use the same message bus as the desktop clients over three tiny HTTP endpoints (plus a translate proxy so their translation requests don't hit CORS):

| Endpoint | Purpose |
| --- | --- |
| `POST /join` | Register a nick + language, returns a session id and the online list |
| `GET /stream?sid=…` | Server-Sent Events stream — live chat / join / leave events |
| `POST /send` | Broadcast a chat message (text + optional Morse) |
| `GET /translate?text=…&tl=…` | Server-side Google Translate proxy |

### Protocol

The desktop client and server exchange one JSON object per line over TCP:

```
client -> server   {"type": "join",  "nick": "...", "lang": "..."}
                   {"type": "chat",  "text": "...", "morse": "..."}

server -> client   {"type": "welcome", "id", "country", "countryCode",
                                      "city", "users": [...]}
                   {"type": "chat",   "nick", "country", "countryCode",
                                      "lang", "text", "morse"}
                   {"type": "join" | "leave", "nick", "country", ...}
```

The plain text always travels alongside the optional Morse variant, so each reader can translate it into their own display language; Morse-mode messages are shown as Morse code.

## Requirements

- Python 3.8+

### To run the server (`server.py`)

- Nothing extra — it uses only the standard library.

### To run the desktop app (`morse.py`)

- `pygame`, `numpy`, `sounddevice` (mic input for Record Mode only):

```bash
pip install pygame numpy sounddevice
```

Note: the Google Translate endpoint is called directly over the public network; if it is unreachable or rate-limited, messages are shown in their original language instead. Web users need no Python at all.