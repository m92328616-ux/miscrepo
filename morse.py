import json
import os
import queue
import socket
import threading
import urllib.parse
import urllib.request

import numpy as np
from functools import lru_cache


MORSE_CODE = {
	"A": ".-", "B": "-...", "C": "-.-.", "D": "-..",
	"E": ".", "F": "..-.", "G": "--.", "H": "....",
	"I": "..", "J": ".---", "K": "-.-", "L": ".-..",
	"M": "--", "N": "-.", "O": "---", "P": ".--.",
	"Q": "--.-", "R": ".-.", "S": "...", "T": "-",
	"U": "..-", "V": "...-", "W": ".--", "X": "-..-",
	"Y": "-.--", "Z": "--..",
	"0": "-----", "1": ".----", "2": "..---", "3": "...--",
	"4": "....-", "5": ".....", "6": "-....", "7": "--...",
	"8": "---..", "9": "----.",
}

_CHARACTER_BY_CODE = {code: character for character, code in MORSE_CODE.items()}

_COMMON_WORDS = (
	"THE", "OF", "AND", "TO", "IN", "IS", "YOU", "THAT", "IT", "HE",
	"WAS", "FOR", "ON", "ARE", "AS", "WITH", "HIS", "THEY", "I", "AT",
	"BE", "THIS", "HAVE", "FROM", "OR", "ONE", "HAD", "BY", "WORD", "BUT",
	"NOT", "WHAT", "ALL", "WERE", "WE", "WHEN", "YOUR", "CAN", "SAID", "THERE",
	"USE", "AN", "EACH", "WHICH", "SHE", "DO", "HOW", "THEIR", "IF", "WILL",
	"UP", "OTHER", "ABOUT", "OUT", "MANY", "THEN", "THEM", "THESE", "SO", "SOME",
	"HER", "WOULD", "MAKE", "LIKE", "HAS", "HIM", "INTO", "TIME", "LOOK", "TWO",
	"MORE", "WRITE", "GO", "SEE", "NUMBER", "NO", "WAY", "COULD", "PEOPLE", "MY",
	"THAN", "FIRST", "WATER", "BEEN", "CALL", "WHO", "OIL", "ITS", "NOW", "FIND",
	"LONG", "DOWN", "DAY", "DID", "GET", "COME", "MADE", "MAY", "PART", "HELLO",
	"WORLD", "YES", "NO", "STOP", "START", "HELP", "MORSE", "SOS",
	"CODE", "CODES", "MACHINE", "MACHINES", "TEST", "TESTS", "QUICK", "BROWN",
	"FOX", "JUMPS", "OVER", "LAZY", "DOG", "INPUT", "OUTPUT", "LETTER", "LETTERS",
	"PREDICT", "PREDICTION", "SIGNAL", "SIGNALS", "DOT", "DOTS", "DASH", "DASHES",
	"SPACE", "SPACES", "BAR", "KEY", "KEYS", "BUTTON", "BUTTONS", "MODE", "MODES",
	"PAUSE", "PAUSES", "FAST", "FASTER", "SLOW", "SLOWER", "NEW", "OLD", "GOOD",
	"BEST", "NEXT", "LAST", "FIRST", "SECOND", "THIRD", "MORNING", "NIGHT", "DAY",
	"WELCOME", "THANK", "THANKS", "PLEASE", "SORRY", "YES", "NO", "READY", "GO",
	"HOME", "WORK", "PLAY", "GAME", "GAMES", "READ", "READER", "LEARN", "LEARNING",
	"KNOW", "THINK", "THINKING", "FEEL", "LOOK", "LISTEN", "SPEAK", "SAY", "TELL",
	"SHOW", "MAKE", "MADE", "TAKE", "GIVE", "KEEP", "HELP", "TRY", "TRYING", "USE",
	"CAN", "MUST", "SHOULD", "MIGHT", "WOULD", "COULD", "WANT", "NEED", "LIKE", "LOVE",
	"LIFE", "LIVE", "LIGHT", "DARK", "RED", "GREEN", "BLUE", "WHITE", "BLACK", "SMALL",
	"LARGE", "BIG", "LONG", "SHORT", "HIGH", "LOW", "LEFT", "RIGHT", "UP", "DOWN",
	"HERE", "THERE", "WHERE", "WHEN", "WHY", "WHO", "HOW", "AGAIN", "BACK", "FORWARD",
	"ARROW", "TREE", "PATH", "ROOT", "BRANCH", "IMAGE", "PICTURE", "BOARD", "REFERENCE",
	"COMMON", "WORD", "WORDS", "ENGLISH", "LANGUAGE", "TEXT", "MESSAGE", "MESSAGES", "HELLO",
	"WORLD", "THING", "THINGS", "PLACE", "PLACES", "PERSON", "PEOPLE", "TIME", "TIMES",
	"YEAR", "YEARS", "WEEK", "MONTH", "TODAY", "TOMORROW", "YESTERDAY", "WATER", "FIRE",
	"EARTH", "AIR", "FOOD", "HOME", "FAMILY", "FRIEND", "FRIENDS", "SCHOOL", "BOOK",
	"BOOKS", "PHONE", "COMPUTER", "PROGRAM", "PROGRAMS", "PYTHON", "WINDOW", "SCREEN",
)

_WORD_BY_MORSE = {}
for _rank, _word in enumerate(_COMMON_WORDS):
	_word_code = "".join(MORSE_CODE[character] for character in _word)
	if _word_code not in _WORD_BY_MORSE:
		_WORD_BY_MORSE[_word_code] = (_rank, _word)

_WORD_RANK = {word: rank for rank, word in enumerate(_COMMON_WORDS)}

# Words indexed by every letter prefix (e.g. "HE" + L -> HELLO, HELP ...) so
# word prediction can match on real letter sequences instead of hunches from
# the merged dot/dash run.  This is built straight from the word list so a
# word whose code collides with another (e.g. HE vs IS both look like
# "....." when merged) is never lost.  Each prefix holds words sorted by
# how common they are.
_WORDS_BY_LETTER_PREFIX = {}
for _word, _rank in sorted(_WORD_RANK.items(), key=lambda _entry: _entry[1]):
	for _index in range(1, len(_word) + 1):
		_WORDS_BY_LETTER_PREFIX.setdefault(_word[:_index], []).append(_word)


CHAT_LANGUAGES = (
	("en", "English"), ("es", "Spanish"), ("pt", "Portuguese"), ("fr", "French"),
	("de", "German"), ("it", "Italian"), ("nl", "Dutch"), ("pl", "Polish"),
	("ru", "Russian"), ("uk", "Ukrainian"), ("sv", "Swedish"), ("tr", "Turkish"),
	("ar", "Arabic"), ("hi", "Hindi"), ("zh-CN", "Chinese"), ("ja", "Japanese"),
	("ko", "Korean"),
)

LANGUAGE_BY_CODE = dict(CHAT_LANGUAGES)

DEFAULT_CHAT_HOST = "127.0.0.1"
DEFAULT_CHAT_PORT = 8765
DEFAULT_CHAT_NICK = os.environ.get("USER") or os.environ.get("USERNAME") or "Operator"

_TRANSLATE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


@lru_cache(maxsize=4096)
def _translate_cached(text, target, source):
	"""Hit the public Google endpoint; raises on failure so failed
	attempts are never cached and get retried later."""
	query = urllib.parse.urlencode(
		{"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
	)
	request = urllib.request.Request(
		_TRANSLATE_ENDPOINT + "?" + query,
		headers={
			"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
			"Referer": "https://translate.google.com/",
		},
	)
	with urllib.request.urlopen(request, timeout=6) as response:
		payload = json.loads(response.read().decode("utf-8"))
	joined = "".join(part[0] for part in payload[0] if part and part[0])
	if not joined:
		raise RuntimeError("empty translation")
	return joined


def google_translate(text, target, source="auto"):
	"""Translate *text* to *target* via the public Google endpoint.

	Returns *text* unchanged if the network is unavailable or the request
	fails, so the chat can never be blocked on translation.
	"""
	if not text or not target:
		return text
	try:
		return _translate_cached(text, target, source)
	except Exception:
		return text


def encode(text):
	"""Convert text to Morse, using / between words."""
	words = text.upper().split()
	return " / ".join(
		" ".join(MORSE_CODE[character] for character in word)
		for word in words
	)


def decode_obvious(morse):
	"""Choose the most likely word or letter split for a Morse run.

	Spaces separate letters, so ``".... ."`` is treated as two letters
	("HE") rather than being silently joined into one run ("....." = 5).
	A complete letter or known word always wins over an invented split.
	"""
	if not morse or not morse.strip():
		return ""
	runs = morse.strip().split()
	if len(runs) > 1:
		return "".join(decode_obvious(run) for run in runs)
	code = runs[0]
	if code in _CHARACTER_BY_CODE:
		return _CHARACTER_BY_CODE[code]
	if code in _WORD_BY_MORSE:
		return _WORD_BY_MORSE[code][1]
	word_split = _best_word_split(code)
	if word_split:
		return " ".join(word_split)
	letter_split = _best_letter_split(code)
	return letter_split or "?"


@lru_cache(maxsize=None)
def _best_word_split(code):
	if not code:
		return ()
	best = None
	for word_code, (rank, word) in _WORD_BY_MORSE.items():
		if not code.startswith(word_code):
			continue
		rest = _best_word_split(code[len(word_code):])
		if rest is None:
			continue
		candidate = (word,) + rest
		candidate_score = (len(candidate), rank + sum(_WORD_BY_MORSE["".join(MORSE_CODE[character] for character in item)][0] for item in rest))
		if best is None or candidate_score < best[0]:
			best = (candidate_score, candidate)
	return None if best is None else best[1]


@lru_cache(maxsize=None)
def _best_letter_split(code):
	if not code:
		return ""
	best = None
	for morse_code, character in _CHARACTER_BY_CODE.items():
		if not code.startswith(morse_code):
			continue
		rest = _best_letter_split(code[len(morse_code):])
		if rest is None:
			continue
		candidate = character + rest
		candidate_score = (len(candidate), -len(morse_code), candidate)
		if best is None or candidate_score < best[0]:
			best = (candidate_score, candidate)
	return None if best is None else best[1]


def decode_timed(signals, letter_pause=420, word_pause=1000):
	"""Decode signals separated by millisecond timestamps.

	Each signal is a ``(dot_or_dash, timestamp_ms)`` pair. Pauses at or above
	letter_pause split letters; longer pauses split words.
	"""
	letters = []
	current = ""
	previous_time = None
	for signal, timestamp in signals:
		if previous_time is not None and current:
			gap = timestamp - previous_time
			if gap >= word_pause:
				letters.append(decode_obvious(current))
				letters.append(" ")
				current = ""
			elif gap >= letter_pause:
				letters.append(decode_obvious(current))
				current = ""
		current += signal
		previous_time = timestamp
	if current:
		letters.append(decode_obvious(current))
	return "".join(letters)


def predict_letters(morse, limit=8):
	"""Return likely characters whose reference-tree paths match a Morse prefix.

	The closest exact match (a complete character) is listed first, then the
	letters that continue the same path.  Numbers are included so a finished
	digit run (e.g. ``"....-"`` = 4) still gets a sensible answer.
	"""
	prefix = "".join(morse.split())
	if not prefix:
		return ("E", "T")
	candidates = [
		(character, code)
		for character, code in MORSE_CODE.items()
		if code.startswith(prefix)
	]
	candidates.sort(
		key=lambda item: (
			len(item[1]) - len(prefix),
			item[1].replace(".", "0").replace("-", "1"),
		)
	)
	return tuple(character for character, _ in candidates[:limit])


@lru_cache(maxsize=None)
def _complete_letters_in_run(code):
	"""Return every letter sequence that fully consumes a dot/dash run."""
	if not code:
		return ("",)
	results = set()
	for morse_code, character in _CHARACTER_BY_CODE.items():
		if not character.isalpha() or not code.startswith(morse_code):
			continue
		for rest in _complete_letters_in_run(code[len(morse_code):]):
			results.add(character + rest)
	return tuple(sorted(results))


@lru_cache(maxsize=None)
def _predict_words(prefix, context=""):
	"""Predict the word the user is spelling from a dot/dash run prefix.

	*prefix* is the Morse for the *current* letter being pressed and
	*context* is the part of the current word already committed (``""`` for
	a fresh word).  Only words whose actual letter sequence starts with the
	context followed by a letter matching the run are suggested, so a run
	never cuts across a letter boundary (``... `` can suggest S/H/V words
	but never ``IS``, which starts with I = ``..``).

	Words whose current letter is already complete win over partial-letter
	guesses, and equally-likely words are ordered by how common they are.
	"""
	prefix = "".join(prefix.split())
	if not prefix:
		return ()
	if not isinstance(context, str) or not context.isalpha():
		context = ""
	else:
		context = context.upper()

	candidates = {}

	def _consider(base, partial):
		for word in _WORDS_BY_LETTER_PREFIX.get(base, ()):
			quality = (partial, _WORD_RANK[word])
			if word not in candidates or quality < candidates[word]:
				candidates[word] = quality

	# Primary interpretation: the run is (part of) one current letter.
	for character in _CHARACTER_BY_CODE.values():
		if not character.isalpha():
			continue
		code = MORSE_CODE[character]
		if code.startswith(prefix):
			_consider(context + character, partial=code != prefix)

	# Fallback: the run could not be (part of) a single character at all,
	# so treat it as one or more complete letters.  A finished number like
	# 5 = "....." is a valid single character, so it is kept out of the
	# word suggestions and the caller falls back to letter prediction.
	if not candidates and not any(
		code.startswith(prefix) for code in MORSE_CODE.values()
	):
		for completed in _complete_letters_in_run(prefix):
			if completed:
				_consider(context + completed, partial=1)

	ordered = sorted(candidates.items(), key=lambda item: (item[1], item[0]))
	return tuple(word for word, _ in ordered[:4])


def decode(morse):
	"""Convert Morse with spaces between letters and / between words to text."""
	words = morse.strip().split("/")
	return " ".join(
		"".join(decode_obvious(code) for code in word.split())
		for word in words
	)


def decode_steps(steps):
	"""Follow the reference sheet's arrows and return the reached letter.

	Left and right arrows represent dashes and dots.  A down arrow is a dot
	on the left side of the sheet and a dash on the right side.
	"""
	if isinstance(steps, str):
		steps = steps.lower().split()

	code = []
	side = None
	for step in steps:
		step = step.lower()
		if step == "left":
			code.append("-")
			side = "left"
		elif step == "right":
			code.append(".")
			side = "right"
		elif step == "down":
			if side is None:
				raise ValueError("down must follow a left or right step")
			code.append("." if side == "left" else "-")
		else:
			raise ValueError("steps must contain only left, right, or down")

	try:
		return _CHARACTER_BY_CODE["".join(code)]
	except KeyError as error:
		raise ValueError("steps do not reach a letter in the Morse tree") from error


class MorseListener:
	"""Capture Morse from the microphone and decode it to text.

	Runs a background thread that samples the mic, detects tone on/off with
	an adaptive, self-calibrating energy threshold, measures each key
	press as a dot or dash by comparing durations relative to each other,
	and uses the gaps between presses to split letters and words.  Decoded
	characters are pushed to ``out_queue`` for the caller to drain.

	Uses FFT-based tonality analysis to filter out human speech and only
	responds to pure tones characteristic of machine-generated Morse code.

	Dot/dash classification uses sliding-window clustering: signal durations
	are collected and the largest natural gap between them is found to
	determine the separation threshold, rather than using fixed ratios.
	"""

	def __init__(self, chunk_ms=15, sample_rate=44100, noise_factor=2.5, min_amp=0.02):
		import queue
		self.sample_rate = sample_rate
		self.chunk_ms = chunk_ms
		self.chunk_size = int(sample_rate * chunk_ms / 1000)
		self.noise_factor = noise_factor
		self.min_amp = min_amp
		self.out_queue = queue.Queue()
		self._partial = [""]
		self._signal_active = [False]
		self._noise_floor = [min_amp]
		self._pending_space = [False]
		self._last_dot_ms = [0.0]
		self._last_dash_ms = [0.0]
		self._last_gap_ms = [0.0]
		self._unit_ms = [90.0]
		self.slow_factor = 1.0
		self._running = False
		self._stream = None
		self._thread = None
		self._buffer = []

		# Sliding-window duration buffer for relative dot/dash classification
		self._duration_buf = []
		self._duration_buf_max = 60
		self._split_ms = [0.0]
		self._split_smooth = [None]
		# First few unclassified signals, held until we can compare them to
		# each other.  None = warm-up over, signals stream immediately.
		self._pending = None
		self._warmup_min = 6

		# Rolling window used for FFT-based speech filtering
		self._tonal_samples = []

		# FFT tonality tracking for speech filtering
		self._is_speech = [False]
		self._tonal_confirm_needed = 3

	@property
	def is_speech(self):
		return self._is_speech[0]

	def start(self):
		"""Open the microphone and begin decoding in the background."""
		import threading
		import sounddevice as sd
		if self._running:
			return
		self._running = True
		self._reset_session()
		self._stream = sd.InputStream(
			samplerate=self.sample_rate,
			channels=1,
			dtype="float32",
			blocksize=self.chunk_size,
			callback=self._fill,
		)
		self._stream.start()
		self._thread = threading.Thread(target=self._run, daemon=True, name="morse-listener")
		self._thread.start()

	def _reset_session(self):
		"""Clear everything learned from a previous recording session."""
		self._buffer = []
		self._is_speech[0] = False
		self._duration_buf = []
		self._split_ms[0] = 0.0
		self._split_smooth[0] = None
		self._unit_ms[0] = 90.0
		self._pending = []
		self._tonal_samples = []

	def _fill(self, indata, frames, time_info, status):
		if status or not self._running:
			return
		self._buffer.extend(indata[:, 0].tolist())

	def stop(self):
		"""Close the microphone and stop the background thread."""
		self._running = False
		if self._stream is not None:
			try:
				self._stream.stop()
				self._stream.close()
			except Exception:
				pass
		if self._thread is not None:
			self._thread.join(timeout=1)
		self._stream = None
		self._thread = None

	@property
	def partial_code(self):
		return self._partial[0]

	@property
	def signal_active(self):
		return self._signal_active[0]

	@property
	def noise_floor(self):
		return self._noise_floor[0]

	@property
	def dot_ms(self):
		return self._last_dot_ms[0]

	@property
	def dash_ms(self):
		return self._last_dash_ms[0]

	@property
	def gap_ms(self):
		return self._last_gap_ms[0]

	@property
	def unit_ms(self):
		return self._unit_ms[0]

	# ---- Speech filtering via FFT tonality analysis ----

	@staticmethod
	def _is_tonal(block, sample_rate):
		"""Return True if *block* sounds like a pure tone (morse beep),
		False if it sounds like speech or broadband noise.

		Computes the FFT of the block, finds the dominant frequency, and
		checks what fraction of total energy lives in a narrow band around
		it.  A pure tone concentrates almost all energy in one peak; speech
	 spreads energy across many frequencies.
		"""
		arr = np.array(block, dtype=np.float32)
		n = len(arr)
		if n < 64:
			return False
		spectrum = np.abs(np.fft.rfft(arr * np.hanning(n)))
		if spectrum.max() < 1e-6:
			return False
		spectrum /= spectrum.max()
		bin_hz = sample_rate / n
		dominant_bin = int(np.argmax(spectrum))
		dominant_freq = dominant_bin * bin_hz
		if dominant_freq < 100 or dominant_freq > 4000:
			return False
		bandwidth_bins = max(int(150 / bin_hz), 2)
		low = max(0, dominant_bin - bandwidth_bins)
		high = min(len(spectrum), dominant_bin + bandwidth_bins + 1)
		tonal_energy = float(np.sum(spectrum[low:high] ** 2))
		total_energy = float(np.sum(spectrum ** 2))
		if total_energy < 1e-12:
			return False
		tonal_ratio = tonal_energy / total_energy
		return tonal_ratio > 0.55

	# ---- Dot/dash clustering via relative comparison ----

	@staticmethod
	def _cluster_threshold(durations):
		"""Find the best dot/dash split within *durations*.

		Returns (threshold, quality) where threshold is the midpoint of the
		largest natural gap between consecutive sorted durations, or
		(None, 0.0) when the durations show no convincing separation (e.g.
		everything is a similar length, so there is no reason to call
		anything a dash).

		With exactly two signals it already works: if one is clearly longer
		than the other (>= 2x), the longer is a dash and the shorter a dot.
		"""
		if len(durations) < 2:
			return None, 0.0
		s = sorted(durations)
		lo, hi = s[0], s[-1]
		if len(s) == 2:
			if hi >= lo * 2.0 and hi - lo >= 25.0:
				return (lo + hi) / 2.0, 1.0
			return None, 0.0
		spread = hi - lo
		if spread < 15.0:
			return None, 0.0
		best_gap = 0.0
		best_idx = 0
		for i in range(1, len(s)):
			gap = s[i] - s[i - 1]
			if gap > best_gap:
				best_gap = gap
				best_idx = i
		quality = best_gap / spread
		if quality < 0.22:
			return None, 0.0
		threshold = (s[best_idx - 1] + s[best_idx]) / 2.0
		return threshold, quality

	def _recompute_threshold(self):
		"""Recompute the dot/dash split and the dot-unit length.

		The returned split is smoothed over time so the boundary doesn't
		flap around.  The unit length (a dot) is the median of the durations
		that fall below the split; it drives letter/word gap logic.
		"""
		if not self._duration_buf:
			return None
		thresh, _ = self._cluster_threshold(self._duration_buf)
		if thresh is None:
			# No convincing separation right now.  Keep any split we already
			# learned this session so real dashes stay valuable, and keep the
			# unit seeded from what we've actually heard (dots dominate, so
			# the median is a good estimate of dot length).
			self._unit_ms[0] = float(np.median(self._duration_buf))
			return self._split_ms[0] or None
		prev = self._split_smooth[0]
		if prev is None:
			prev = thresh
		else:
			prev = 0.7 * prev + 0.3 * thresh
		self._split_smooth[0] = prev
		self._split_ms[0] = prev
		shorts = [d for d in self._duration_buf if d < prev]
		if shorts:
			self._unit_ms[0] = float(np.median(shorts))
		else:
			self._unit_ms[0] = prev / 2.5
		return prev

	# ---- Core processing loop ----

	def _run(self):
		import time

		noise_floor = self.min_amp
		key_active = False
		confirm = 0
		key_start_samples = 0
		last_key_end_samples = None
		offset = 0
		tonal_chunks = 0
		non_tonal_chunks = 0
		tonal_win = self._tonal_samples

		while self._running:
			if not self._buffer:
				time.sleep(self.chunk_ms / 1000.0)
				continue
			block = self._buffer[:self.chunk_size]
			del self._buffer[:len(block)]
			if len(block) < self.chunk_size:
				time.sleep(0.002)
				continue

			energy = float(np.sqrt(np.mean(np.array(block) ** 2)))
			now_samples = offset + self.chunk_size
			offset = now_samples
			stretch = self.slow_factor
			unit = self._unit_ms[0] or 90.0

			# --- Speech filtering via FFT tonality analysis ---
			# Use a rolling ~90ms window so short dots still get enough
			# samples for the frequency analysis to be meaningful.
			tonal_win.extend(block)
			if len(tonal_win) > 4000:
				del tonal_win[:-3200]
			is_tonal_chunk = self._is_tonal(tonal_win, self.sample_rate)
			if energy > noise_floor * 1.2:
				if is_tonal_chunk:
					tonal_chunks += 1
					non_tonal_chunks = max(0, non_tonal_chunks - 1)
				else:
					non_tonal_chunks += 1
					tonal_chunks = max(0, tonal_chunks - 1)
			total_chunks = tonal_chunks + non_tonal_chunks
			if total_chunks >= self._tonal_confirm_needed:
				tonal_ratio = tonal_chunks / total_chunks
				if tonal_ratio < 0.45:
					self._is_speech[0] = True
				else:
					self._is_speech[0] = False
				# Decay counters to adapt to changing audio
				tonal_chunks = int(tonal_chunks * 0.85)
				non_tonal_chunks = int(non_tonal_chunks * 0.85)

			# --- Noise floor tracking ---
			if energy < noise_floor:
				noise_floor = max(self.min_amp, noise_floor * 0.9 + energy * 0.1)
			threshold = max(self.min_amp, noise_floor * self.noise_factor)

			# --- Key on/off detection (skip if speech detected) ---
			if not key_active:
				if energy >= threshold:
					confirm += 1
					if confirm >= 2:
						if (self._pending_space[0] and not self._is_speech[0]
								and last_key_end_samples is not None):
							gap_check = (
								(now_samples - last_key_end_samples)
								* 1000.0 / self.sample_rate * stretch / unit
							)
							if gap_check >= 4.4:
								self.out_queue.put(" ")
							self._pending_space[0] = False
						key_active = True
						self._signal_active[0] = True
						key_start_samples = now_samples
				else:
					confirm = 0
			else:
				self._noise_floor[0] = noise_floor
				if energy < threshold:
					confirm += 1
					if confirm >= 2:
						key_active = False
						self._signal_active[0] = False
						duration_ms = (now_samples - key_start_samples) * 1000.0 / self.sample_rate * stretch

						if self._is_speech[0]:
							# Reset partial code when speech ends
							if self._partial[0]:
								self._partial[0] = ""
							last_key_end_samples = now_samples
							continue

						if last_key_end_samples is not None:
							gap_ms = (key_start_samples - last_key_end_samples) * 1000.0 / self.sample_rate * stretch
						else:
							gap_ms = 0.0
						last_key_end_samples = now_samples
						self._classify(duration_ms, gap_ms)
				else:
					confirm = 0

			# Auto-commit trailing letter after quiet stretch
			if not key_active and last_key_end_samples is not None and not self._is_speech[0]:
				idle_units = (
					(now_samples - last_key_end_samples)
					* 1000.0 / self.sample_rate * stretch / unit
				)
				if idle_units >= 2.4:
					if self._pending:
						# A short transmission has ended while still in
						# warm-up; classify what we heard and release it.
						for d, g in self._pending:
							self._emit_signal(d, g, self._split_ms[0] or None)
						self._pending = None
					if self._partial[0]:
						self.out_queue.put(decode_obvious(self._partial[0]))
						self._partial[0] = ""
						self._pending_space[0] = True

	def _classify(self, duration_ms, gap_ms):
		"""Classify a key press duration as dot or dash using relative comparison.

		During warm-up the first few signals are held back and classified
		retroactively once the durations can be compared to each other, so
		the very first dash+dot pair is already told apart.  After that each
		signal streams immediately through the learned split point.  The
		learned dot-unit also drives the gap logic that splits letters and
		words, so everything scales with the sender's speed.
		"""
		if duration_ms <= 0:
			return

		# Keep the recent durations; the split is re-learned from this window.
		self._duration_buf.append(duration_ms)
		if len(self._duration_buf) > self._duration_buf_max:
			self._duration_buf = self._duration_buf[-self._duration_buf_max:]
		split = self._recompute_threshold()

		if self._pending is not None:
			# Warm-up: buffer until we can compare these signals to each other.
			self._pending.append((duration_ms, gap_ms))
			need_split = split is not None and len(self._pending) >= 2
			need_more = len(self._pending) >= self._warmup_min
			if not (need_split or need_more):
				return
			for d, g in self._pending:
				self._emit_signal(d, g, split)
			self._pending = None
			return

		self._emit_signal(duration_ms, gap_ms, split)

	def _emit_signal(self, duration_ms, gap_ms, split):
		"""Turn one measured press into a dot/dash and fold it into a letter."""
		if duration_ms <= 0:
			return

		if split is not None:
			# Relative comparison against the learned boundary.
			dash = duration_ms >= split
		else:
			# No learned split yet (e.g. everything so far is a similar
			# length): dots dominate in Morse, so only treat clearly-long
			# presses as dashes.
			unit = self._unit_ms[0] or 90.0
			dash = duration_ms >= unit * 2.2

		if dash:
			signal = "-"
			self._last_dash_ms[0] = duration_ms
		else:
			signal = "."
			self._last_dot_ms[0] = duration_ms
		self._last_gap_ms[0] = gap_ms

		# Gap-based letter/word splitting, scaled by the learned dot-unit.
		unit = self._unit_ms[0] or 90.0
		previous = self._partial[0]
		if previous:
			if gap_ms >= unit * 4.4:
				self.out_queue.put(decode_obvious(previous))
				self.out_queue.put(" ")
				self._partial[0] = ""
			elif gap_ms >= unit * 2.2:
				self.out_queue.put(decode_obvious(previous))
				self._partial[0] = ""
		self._partial[0] = self._partial[0] + signal

	def flush(self):
		"""Commit the current partial letter without adding a trailing space.
		Also flushes any signal still waiting in the warm-up buffer."""
		if self._pending:
			for d, g in self._pending:
				self._emit_signal(d, g, self._split_ms[0] or None)
			self._pending = None
		if self._partial[0]:
			self.out_queue.put(decode_obvious(self._partial[0]))
			self._partial[0] = ""


def _wrap_chat(text, measure=None):
	"""Break a chat message into lines of at most 1080px.

	*measure* returns the pixel width of a candidate line.  When omitted a
	conservative character-count estimate is used so the helper is usable
	standalone (e.g. in tests) without a font object.
	"""
	if measure is None:
		measure = lambda candidate: len(candidate) * 16
	lines = []
	current = ""
	for word in str(text).split():
		candidate = f"{current} {word}".strip()
		if measure(candidate) <= 1080:
			current = candidate
			continue
		if current:
			lines.append(current)
		current = word
	if current:
		lines.append(current)
	return lines or [" "]


def chat_rendering(morse_code, translated):
	"""Build the chat-log lines and optional note for a message.

	A real Morse code string is shown verbatim with a note holding the
	translation; anything else (plain text, or a stray boolean/status value)
	falls back to displaying the text itself so a status flag can never leak
	into the visible output.
	"""
	if isinstance(morse_code, str) and morse_code:
		return _wrap_chat(morse_code), "-> " + translated
	return _wrap_chat(translated), None


def encode_words_to_morse(text):
	"""Convert a chat message to space-separated Morse with / between words."""
	words = []
	for word in text.split():
		cleaned = "".join(character for character in word.upper() if character in MORSE_CODE)
		if cleaned:
			words.append(" ".join(MORSE_CODE[character] for character in cleaned))
	return " / ".join(words) if words else None


def decode_morse_entry(buffer):
	"""Decode chat Morse input: words are separated by / and letters by spaces."""
	decoded = []
	for word in buffer.strip().split(" / "):
		letters = [letter for letter in word.split() if letter]
		if letters:
			decoded.append("".join(
				_CHARACTER_BY_CODE.get(letter) or decode_obvious(letter)
				for letter in letters
			))
	return " ".join(decoded)


class _Translator:
	"""Background worker that translates incoming chat messages, so the
	pygame loop is never blocked by a network call to Google."""

	def __init__(self):
		self._jobs = queue.Queue()
		self._thread = threading.Thread(daemon=True, name="chat-translator", target=self._run)
		self._thread.start()

	def submit(self, callback, text, target):
		self._jobs.put((callback, text, target))

	def _run(self):
		while True:
			callback, text, target = self._jobs.get()
			if not text or not target:
				callback(text)
				continue
			callback(google_translate(text, target))


class MorseChatClient:
	"""Non-blocking TCP client for the international Morse chat server."""

	def __init__(self, host, port, nick, lang="en"):
		self.host = host
		self.port = port
		self.nick = nick
		self.lang = lang
		self.sock = None
		self._running = False
		self._thread = None
		self._read_buffer = b""
		self._send_lock = threading.Lock()
		self.inbox = queue.Queue()
		self.outbox = queue.Queue()
		self.connected = False
		self.status_text = "disconnected"
		self.country = ""
		self.country_code = "--"
		self.city = ""
		self.users = []

	def start(self):
		if self._thread is not None and self._thread.is_alive():
			return
		self._running = True
		self._thread = threading.Thread(daemon=True, name="morse-chat-client", target=self._run)
		self._thread.start()

	def _run(self):
		self.connected = False
		self.status_text = "connecting"
		sock = None
		error = None
		try:
			sock = socket.create_connection((self.host, self.port), timeout=8)
			sock.settimeout(0.25)
			self.sock = sock
			self.status_text = "handshake"
			self._send({"type": "join", "nick": self.nick, "lang": self.lang})
			while self._running:
				while not self.outbox.empty():
					self._send(self.outbox.get_nowait())
				try:
					chunk = sock.recv(4096)
				except socket.timeout:
					continue
				if not chunk:
					break
				self._read_buffer += chunk
				while b"\n" in self._read_buffer:
					line, _, self._read_buffer = self._read_buffer.partition(b"\n")
					self._handle_line(line.decode("utf-8", "replace"))
		except OSError as exc:
			error = str(exc)
		finally:
			self.connected = False
			self.status_text = f"error: {error}" if error and self._running else "disconnected"
			try:
				if sock is not None:
					sock.close()
			except OSError:
				pass
			self.sock = None

	def _send(self, packet):
		if self.sock is None:
			return
		data = (json.dumps(packet, ensure_ascii=False) + "\n").encode("utf-8")
		with self._send_lock:
			try:
				self.sock.sendall(data)
			except OSError:
				pass

	def send_chat(self, text, morse=None):
		self.outbox.put({"type": "chat", "text": text, "morse": morse or None})

	def _handle_line(self, line):
		try:
			msg = json.loads(line)
		except ValueError:
			return
		msg_type = msg.get("type")
		if msg_type == "welcome":
			self.connected = True
			self.status_text = "connected"
			self.country = msg.get("country", "")
			self.country_code = msg.get("countryCode", "--")
			self.city = msg.get("city", "")
			self.users = msg.get("users", [])
		elif msg_type == "join":
			self.users.append({
				"nick": msg.get("nick", "?"),
				"country": msg.get("country", ""),
				"code": msg.get("countryCode", "--"),
			})
			self.inbox.put(msg)
		elif msg_type == "leave":
			self.users = [user for user in self.users if user.get("nick") != msg.get("nick")]
			self.inbox.put(msg)
		elif msg_type == "chat":
			self.inbox.put(msg)

	def disconnect(self):
		self._running = False
		try:
			if self.sock is not None:
				self.sock.shutdown(socket.SHUT_RDWR)
		except OSError:
			pass
		try:
			if self.sock is not None:
				self.sock.close()
		except OSError:
			pass
		if self._thread is not None:
			self._thread.join(timeout=2)
		self._thread = None
		self.sock = None
		self.connected = False
		self.status_text = "disconnected"


def run_machine(config=None):
	"""Run a pygame Morse keyer controlled by the space bar."""
	cfg = config or {}
	chat_host = str(cfg.get("server") or DEFAULT_CHAT_HOST)
	chat_port = int(cfg.get("port") or DEFAULT_CHAT_PORT)
	chat_nick = str(cfg.get("nick") or DEFAULT_CHAT_NICK).strip()[:24] or "Operator"
	chat_display_lang = str(cfg.get("lang") or "en")
	if chat_display_lang not in LANGUAGE_BY_CODE:
		chat_display_lang = "en"
	auto_connect = bool(cfg.get("connect"))
	chat_client = None
	chat_translator = None
	chat_log = []
	chat_input = ""
	chat_mode = "normal"
	chat_lang_open = False
	chat_lang_scroll = 0
	import array
	import math
	import pygame

	pygame.mixer.pre_init(44100, -16, 1, 512)
	pygame.init()
	screen = pygame.display.set_mode((1200, 720))
	pygame.display.set_caption("Morse Machine")
	title_font = pygame.font.Font(None, 64)
	font = pygame.font.Font(None, 32)
	label_font = pygame.font.Font(None, 30)
	large_font = pygame.font.Font(None, 112)
	clock = pygame.time.Clock()
	try:
		pygame.mixer.init()
		audio_enabled = True
	except pygame.error:
		audio_enabled = False

	background = (12, 18, 27)
	panel = (24, 34, 47)
	panel_highlight = (31, 44, 59)
	text_color = (235, 240, 245)
	muted_text = (156, 171, 187)
	accent = (77, 201, 176)
	dash_color = (242, 186, 73)
	accent_soft = (45, 88, 91)
	dash_threshold = 180
	dot_interval = 150
	checker_interval = 10
	letter_gap = 700
	word_gap = 1400
	mode_options = ("Duration Mode", "Dot Stream Mode", "Keyboard Buttons", "Translator Mode", "Record Mode", "International Chat")
	mode = mode_options[0]
	dropdown_open = False
	speed_dropdown_open = False
	speed_options = (0.25, 0.5, 1, 1.25, 1.5, 2)
	playback_speed = 1
	current_code = ""
	message = ""
	press_started = None
	last_dot = None
	dot_emitted = False
	last_signal = None
	last_check = pygame.time.get_ticks()
	translator_text = ""
	help_root = None
	help_window = None
	running = True
	dropdown_rect = pygame.Rect(55, 270, 350, 52)
	sound_button_rect = pygame.Rect(975, 270, 150, 52)
	speed_button_rect = pygame.Rect(800, 270, 155, 52)
	record_slowmo_rect = pygame.Rect(800, 270, 155, 52)
	record_slow_options = (1.0, 2.0, 3.0, 4.0)
	record_slow_index = 0
	listener = MorseListener()

	chat_mode_rect = pygame.Rect(455, 270, 245, 52)
	chat_lang_rect = pygame.Rect(710, 270, 175, 52)
	chat_status_rect = pygame.Rect(895, 270, 230, 52)

	def load_chat_font(size):
		for path in (
			"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
			"/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
		):
			if os.path.exists(path):
				try:
					return pygame.font.Font(path, size)
				except Exception:
					pass
		return pygame.font.Font(None, size)

	chat_font = load_chat_font(30)

	def make_tone(duration_ms):
		sample_rate = 44100
		frequency = 700
		samples = array.array("h")
		for index in range(int(sample_rate * duration_ms / 1000)):
			envelope = min(1.0, index / 300, (int(sample_rate * duration_ms / 1000) - index) / 600)
			value = int(12000 * envelope * math.sin(2 * math.pi * frequency * index / sample_rate))
			samples.append(value)
		return pygame.mixer.Sound(buffer=samples.tobytes())

	def make_morse_audio(morse_text):
		sample_rate = 44100
		frequency = 700
		samples = array.array("h")
		speed = playback_speed

		def silence(duration_ms):
			samples.extend([0] * int(sample_rate * duration_ms / 1000))

		def tone(duration_ms):
			count = int(sample_rate * duration_ms / 1000)
			for index in range(count):
				envelope = min(1.0, index / 300, (count - index) / 600)
				value = int(12000 * envelope * math.sin(2 * math.pi * frequency * index / sample_rate))
				samples.append(value)

		for index, symbol in enumerate(morse_text):
			if symbol == ".":
				tone(90 / speed)
				silence(90 / speed)
			elif symbol == "-":
				tone(240 / speed)
				silence(90 / speed)
			elif symbol == " ":
				silence(150 / speed)
			elif symbol == "/":
				silence(400 / speed)
		return pygame.mixer.Sound(buffer=samples.tobytes())

	if audio_enabled:
		dot_sound = make_tone(90)
		dash_sound = make_tone(240)
		sound_channel = pygame.mixer.Channel(0)
	else:
		dot_sound = dash_sound = sound_channel = None

	def play_code(code):
		if not audio_enabled or dot_sound is None or dash_sound is None or sound_channel is None:
			return
		sounds = [dot_sound if symbol == "." else dash_sound for symbol in code if symbol in ".-"]
		if not sounds:
			return
		sound_channel.play(sounds[0])
		for sound in sounds[1:]:
			sound_channel.queue(sound)

	def play_signal(signal):
		if audio_enabled and dot_sound is not None and dash_sound is not None:
			(dot_sound if signal == "." else dash_sound).play()

	def play_current():
		if mode == "Translator Mode":
			morse_output = encode(translator_text)
		else:
			morse_output = encode(message)
		if audio_enabled and morse_output and sound_channel is not None:
			sound_channel.play(make_morse_audio(morse_output))

	def commit_letter():
		nonlocal current_code, message
		if not current_code:
			return
		message += decode_obvious(current_code)
		current_code = ""

	def record_signal(signal, signal_time):
		nonlocal current_code, message, last_signal
		if last_signal is not None and current_code:
			gap = signal_time - last_signal
			if gap >= word_gap:
				commit_letter()
				if message and not message.endswith(" "):
					message += " "
			elif gap >= letter_gap:
				commit_letter()
		current_code += signal
		last_signal = signal_time

	def select_mode(selected_mode):
		nonlocal mode, current_code, press_started, last_dot, dot_emitted, last_signal, chat_client
		if mode == "Record Mode":
			listener.flush()
			listener.stop()
		mode = selected_mode
		current_code = ""
		press_started = None
		last_dot = None
		dot_emitted = False
		last_signal = None
		if mode == "Translator Mode":
			pygame.key.start_text_input()
		elif mode == "International Chat":
			pygame.key.start_text_input()
			if chat_client is None:
				start_chat()
		elif mode == "Record Mode":
			pygame.key.stop_text_input()
			try:
				listener.start()
			except Exception:
				pass
		else:
			pygame.key.stop_text_input()

	def check_pattern(check_time):
		nonlocal message
		if last_signal is None or press_started is not None:
			return
		idle_time = check_time - last_signal
		if current_code and idle_time >= letter_gap:
			commit_letter()
		if (
			not current_code
			and message
			and idle_time >= word_gap
			and not message.endswith(" ")
		):
			message += " "

	def draw_message(text, area):
		if not text:
			message_font = pygame.font.Font(None, 86)
			screen.blit(message_font.render("|", True, text_color), area.topleft)
			return

		message_font = pygame.font.Font(None, 86)
		lines = []
		line_height = 40
		for size in range(72, 17, -2):
			message_font = pygame.font.Font(None, size)
			lines = []
			for paragraph in text.split("\n"):
				line = ""
				for word in paragraph.split():
					remaining = word
					while remaining:
						candidate = f"{line} {remaining}".strip()
						if message_font.size(candidate)[0] <= area.width:
							line = candidate
							break
						if line:
							lines.append(line)
							line = ""
							continue
						chunk = ""
						for character in remaining:
							if message_font.size(chunk + character)[0] > area.width:
								break
							chunk += character
						if not chunk:
							break
						line = chunk
						remaining = remaining[len(chunk):]
						if remaining:
							lines.append(line)
							line = ""
				if line:
					lines.append(line)
			if not lines:
				lines.append("")
			line_height = message_font.get_linesize()
			if len(lines) * line_height <= area.height:
				break

		if len(lines) * line_height > area.height:
				lines = lines[-5:]
				lines[0] = "... " + lines[0]

		for index, line in enumerate(lines):
			screen.blit(
				message_font.render(line, True, text_color),
				(area.x, area.y + index * line_height),
			)

	def draw_morse(code, area, show_cursor):
		symbols = list(code)
		if show_cursor:
			symbols.append("|")
		morse_font = pygame.font.Font(None, 56)
		lines = [[]]
		line_height = 0
		for size in range(82, 19, -2):
			morse_font = pygame.font.Font(None, size)
			lines = [[]]
			line_width = 0
			for symbol in symbols:
				symbol_width = morse_font.size(symbol)[0] + 16
				if lines[-1] and line_width + symbol_width > area.width:
					lines.append([])
					line_width = 0
				lines[-1].append(symbol)
				line_width += symbol_width
			line_height = morse_font.get_linesize()
			if len(lines) * line_height <= area.height:
				break

		if len(lines) * line_height > area.height:
			lines = lines[-3:]
			lines[0].insert(0, "...")
		for row, line in enumerate(lines):
			x_position = area.x
			for symbol in line:
				color = text_color if symbol == "|" or symbol == "..." else accent if symbol == "." else dash_color
				symbol_surface = morse_font.render(symbol, True, color)
				screen.blit(symbol_surface, (x_position, area.y + row * line_height))
				x_position += symbol_surface.get_width() + 16

	def draw_translation(text, area):
		if not text:
			screen.blit(font.render("Type a word or phrase...", True, muted_text), area.topleft)
			return

		items = []
		for character in text.upper():
			if character == " ":
				items.append(" ")
			elif character in MORSE_CODE:
					items.append((character, MORSE_CODE[character]))
		translation_font = pygame.font.Font(None, 30)
		morse_font = pygame.font.Font(None, 30)
		lines = [[]]
		line_height = 0
		for size in range(34, 13, -2):
			translation_font = pygame.font.Font(None, max(size - 4, 12))
			morse_font = pygame.font.Font(None, size)
			lines = [[]]
			line_width = 0
			for item in items:
				if item == " ":
					line_width += morse_font.size("  ")[0]
					continue
				character, code = item
				item_width = max(
					translation_font.size(f"[{character}]")[0],
					morse_font.size(code)[0],
				) + 18
				if lines[-1] and line_width + item_width > area.width:
					lines.append([])
					line_width = 0
				lines[-1].append(item)
				line_width += item_width
			line_height = max(translation_font.get_linesize() + 4, morse_font.get_linesize()) + 8
			if len(lines) * line_height <= area.height:
				break

		if len(lines) * line_height > area.height:
			lines = lines[-3:]
			lines[0].insert(0, ("...", ""))
		label_height = translation_font.get_linesize()
		morse_height = morse_font.get_linesize()
		for row, line in enumerate(lines):
			x_position = area.x
			y_position = area.y + row * line_height
			for character, code in line:
				label = translation_font.render(f"[{character}]", True, accent)
				pattern = morse_font.render(code, True, text_color)
				screen.blit(label, (x_position, y_position))
				screen.blit(pattern, (x_position, y_position + label_height + (line_height - label_height - morse_height) // 2))
				x_position += max(label.get_width(), pattern.get_width()) + 18

	def show_help():
		nonlocal help_root, help_window
		import tkinter as tk

		if help_window is not None:
			if help_window.winfo_viewable():
				help_window.withdraw()
			else:
				help_window.deiconify()
				help_window.lift()
			return

		help_root = tk.Tk()
		help_root.withdraw()
		help_window = tk.Toplevel(help_root)
		help_window.title("Morse Code List")
		help_window.geometry("620x300")
		help_window.configure(bg="#18222f")
		help_window.protocol("WM_DELETE_WINDOW", help_window.withdraw if help_window is not None else (lambda: None))
		help_window.bind("<Tab>", lambda _event: help_window.withdraw() if help_window is not None else None)

		title = tk.Label(
			help_window,
			text="MORSE CODE LIST",
			bg="#18222f",
			fg="#4dc9b0",
			font=("DejaVu Sans", 16, "bold"),
		)
		title.pack(pady=(16, 10))
		paragraph = "    ".join(
			f"{character}:{code}" for character, code in MORSE_CODE.items()
		)
		body = tk.Label(
			help_window,
			text=paragraph,
			bg="#1f2c3b",
			fg="#ebf0f5",
			font=("DejaVu Sans Mono", 12),
			justify="left",
			anchor="nw",
			padx=14,
			pady=14,
			wraplength=580,
		)
		body.pack(fill="both", expand=True, padx=18, pady=(0, 18))

	def update_help():
		if help_root is None:
			return
		try:
			help_root.update_idletasks()
			help_root.update()
		except Exception:
			pass

	def start_chat():
		nonlocal chat_client, chat_translator
		if chat_client is not None:
			chat_client.disconnect()
		chat_client = MorseChatClient(chat_host, chat_port, chat_nick, lang=chat_display_lang)
		chat_client.start()
		if chat_translator is None:
			chat_translator = _Translator()

	def toggle_chat():
		nonlocal chat_client
		if chat_client is not None and chat_client.connected:
			chat_client.disconnect()
			chat_client = None
		else:
			start_chat()

	def wrap_chat(text):
		return _wrap_chat(text, measure=lambda candidate: chat_font.size(candidate)[0])

	def submit_translation(entry, text, morse_code):
		if chat_translator is None or not text:
			return

		def apply(translated):
			lines, note = chat_rendering(morse_code, translated)
			entry["lines"] = lines
			if note is not None:
				entry["note"] = note

		chat_translator.submit(apply, text, chat_display_lang)

	def same_lang_prefix(first, second):
		return (first or "").lower().split("-")[0] == (second or "").lower().split("-")[0]

	def add_chat_message(msg):
		nonlocal chat_log
		msg_type = msg.get("type")
		if msg_type == "join":
			chat_log.append({"kind": "system", "lines": [f"+ {msg.get('nick', '?')} joined from {msg.get('country', '?')}"]})
		elif msg_type == "leave":
			chat_log.append({"kind": "system", "lines": [f"- {msg.get('nick', '?')} left"]})
		elif msg_type == "chat":
			text = msg.get("text") or ""
			morse = msg.get("morse") or ""
			nick = msg.get("nick") or "?"
			country = msg.get("country") or msg.get("countryCode") or ""
			if morse:
				entry = {"kind": "chat", "nick": nick, "country": country, "lines": wrap_chat(morse)}
				chat_log.append(entry)
				submit_translation(entry, text, morse)
			elif text:
				entry = {"kind": "chat", "nick": nick, "country": country, "lines": wrap_chat(text)}
				chat_log.append(entry)
				if not same_lang_prefix(msg.get("lang"), chat_display_lang):
					submit_translation(entry, text, None)
		if len(chat_log) > 300:
			del chat_log[:50]

	def morse_space():
		nonlocal chat_input
		if not chat_input or chat_input.rstrip().endswith("/"):
			return
		if chat_input.endswith(" "):
			chat_input = chat_input.rstrip() + " / "
		else:
			chat_input += " "

	def morse_slash():
		nonlocal chat_input
		if not chat_input or chat_input.rstrip().endswith("/"):
			return
		chat_input = chat_input.rstrip() + " / "

	def send_chat_message():
		nonlocal chat_input
		text = chat_input.strip()
		morse = None
		if chat_mode == "morse_to_word":
			morse = text or None
			text = decode_morse_entry(morse) or text
		elif chat_mode == "words_to_morse":
			morse = encode_words_to_morse(text)
		if not text:
			return
		if chat_client is None or not chat_client.connected:
			return
		chat_client.send_chat(text, morse)
		add_chat_message({
			"type": "chat",
			"nick": chat_nick,
			"country": chat_client.country,
			"lang": chat_display_lang,
			"text": text,
			"morse": morse,
		})
		chat_input = ""

	def draw_chat_screen(now):
		nonlocal chat_lang_scroll
		screen.fill(background)
		pygame.draw.rect(screen, (15, 30, 40), (0, 0, 1200, 180))
		screen.blit(title_font.render("INTERNATIONAL CHAT", True, text_color), (55, 38))
		screen.blit(font.render("Talk to the world — or send the whole message in Morse", True, accent), (58, 105))

		connected = chat_client is not None and chat_client.connected
		if connected:
			place = "?"
			if chat_client is not None:
				place = chat_client.country or chat_client.country_code or "?"
			status = f"CONNECTED · YOU: {chat_nick} · {place}"
			status_color = accent
		elif chat_client is not None and chat_client.status_text == "connecting":
			status = "CONNECTING..."
			status_color = (242, 186, 73)
		elif chat_client is not None and chat_client.status_text:
			status = chat_client.status_text.upper()
			status_color = muted_text
		else:
			status = "DISCONNECTED"
			status_color = muted_text
		screen.blit(font.render(status, True, status_color), (58, 140))
		if chat_client is not None:
			online_names = ", ".join(user.get("nick", "?") for user in chat_client.users)
			online = f"{len(chat_client.users)} ONLINE: {online_names}"
		else:
			online = "0 ONLINE"
		screen.blit(font.render(online, True, muted_text), (58, 174))

		pygame.draw.rect(screen, panel, (35, 215, 1130, 145), border_radius=12)
		screen.blit(label_font.render("OPTIONS", True, accent), (55, 232))
		mode_label = {
			"normal": "TEXT",
			"morse_to_word": "MORSE>WORD",
			"words_to_morse": "WORDS>MORSE",
		}[chat_mode]
		mode_active = chat_mode != "normal"
		pygame.draw.rect(screen, accent_soft if mode_active else panel_highlight, chat_mode_rect, border_radius=8)
		screen.blit(chat_font.render("CHAT MODE", True, text_color), (chat_mode_rect.x + 12, chat_mode_rect.y + 6))
		screen.blit(chat_font.render(mode_label, True, dash_color if mode_active else muted_text), (chat_mode_rect.x + 12, chat_mode_rect.y + 32))
		pygame.draw.rect(screen, panel_highlight, chat_lang_rect, border_radius=8)
		lang_name = LANGUAGE_BY_CODE.get(chat_display_lang, chat_display_lang)
		screen.blit(chat_font.render(f"LANG: {lang_name}", True, text_color), (chat_lang_rect.x + 12, chat_lang_rect.y + 14))
		pygame.draw.rect(screen, panel_highlight if connected else accent_soft, chat_status_rect, border_radius=8)
		screen.blit(chat_font.render("DISCONNECT" if connected else "CONNECT", True, text_color), (chat_status_rect.x + 12, chat_status_rect.y + 14))

		log_rect = pygame.Rect(35, 390, 1130, 235)
		pygame.draw.rect(screen, panel, log_rect, border_radius=12)
		rows = []
		for entry in chat_log:
			if entry["kind"] == "system":
				for line in entry["lines"]:
					rows.append((line, muted_text))
				continue
			header = entry["nick"]
			if entry.get("country"):
				header += f"  [{entry['country']}]"
			rows.append((header, accent))
			for line in entry["lines"]:
				rows.append((line, text_color))
			if entry.get("note"):
				rows.append((entry["note"], muted_text))
		line_height = chat_font.get_linesize() + 2
		max_rows = (log_rect.height - 20) // line_height
		visible = rows[-max_rows:]
		row_y = log_rect.y + 10
		for text, color in visible:
			screen.blit(chat_font.render(text, True, color), (log_rect.x + 14, row_y))
			row_y += line_height
		if not chat_log:
			hint = "Connect and start typing…"
			screen.blit(chat_font.render(hint, True, muted_text), (log_rect.x + 14, log_rect.y + 12))

		input_rect = pygame.Rect(35, 634, 1130, 82)
		pygame.draw.rect(screen, panel_highlight, input_rect, border_radius=10)
		caret = "|" if now // 500 % 2 == 0 else " "
		if chat_mode == "morse_to_word":
			prefix = "MORSE>WORD:"
			prefix_surface = chat_font.render(prefix, True, dash_color)
			screen.blit(prefix_surface, (input_rect.x + 14, input_rect.y + 10))
			value = (chat_input + caret) if chat_input else caret
			screen.blit(chat_font.render(value, True, text_color), (input_rect.x + 14 + prefix_surface.get_width(), input_rect.y + 10))
			preview = "-> " + (decode_morse_entry(chat_input) if chat_input else "press . - space / to type morse, Enter to send")
			screen.blit(chat_font.render(preview, True, muted_text), (input_rect.x + 14, input_rect.y + 48))
		else:
			prefix = "WORDS>MORSE:" if chat_mode == "words_to_morse" else "TEXT:"
			prefix_surface = chat_font.render(prefix, True, dash_color if chat_mode == "words_to_morse" else accent)
			screen.blit(prefix_surface, (input_rect.x + 14, input_rect.y + 20))
			value = (chat_input + caret) if chat_input else caret
			screen.blit(chat_font.render(value, True, text_color), (input_rect.x + 14 + prefix_surface.get_width(), input_rect.y + 20))

		if chat_lang_open:
			visible = max(1, (720 - (chat_lang_rect.y + 52)) // 34)
			max_scroll = max(0, len(CHAT_LANGUAGES) - visible)
			chat_lang_scroll = min(max_scroll, max(0, chat_lang_scroll))
			for index in range(chat_lang_scroll, min(len(CHAT_LANGUAGES), chat_lang_scroll + visible)):
				code, name = CHAT_LANGUAGES[index]
				option_rect = pygame.Rect(chat_lang_rect.x, chat_lang_rect.y + 52 + (index - chat_lang_scroll) * 34, chat_lang_rect.width, 34)
				pygame.draw.rect(screen, panel_highlight, option_rect, border_radius=6)
				pygame.draw.rect(screen, accent_soft, option_rect, width=1, border_radius=6)
				marker = " *" if code == chat_display_lang else ""
				screen.blit(chat_font.render(name + marker, True, text_color), (option_rect.x + 8, option_rect.y + 6))

	if auto_connect:
		select_mode("International Chat")

	while running:
		now = pygame.time.get_ticks()
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				running = False
			elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
				if mode == "International Chat" and chat_status_rect.collidepoint(event.pos):
					toggle_chat()
				elif mode == "International Chat" and chat_mode_rect.collidepoint(event.pos):
					_chat_order = ("normal", "morse_to_word", "words_to_morse")
					chat_mode = _chat_order[(_chat_order.index(chat_mode) + 1) % len(_chat_order)]
					chat_lang_open = False
				elif mode == "International Chat" and chat_lang_rect.collidepoint(event.pos):
					chat_lang_open = not chat_lang_open
					if chat_lang_open:
						_selected = next((_i for _i, (_code, _name) in enumerate(CHAT_LANGUAGES) if _code == chat_display_lang), 0)
						_visible = max(1, (720 - (chat_lang_rect.y + 52)) // 34)
						chat_lang_scroll = min(max(0, _selected - _visible // 2), max(0, len(CHAT_LANGUAGES) - _visible))
				elif mode == "International Chat" and chat_lang_open:
					_visible = max(1, (720 - (chat_lang_rect.y + 52)) // 34)
					for _index in range(chat_lang_scroll, min(len(CHAT_LANGUAGES), chat_lang_scroll + _visible)):
						_code, _name = CHAT_LANGUAGES[_index]
						_option_rect = pygame.Rect(chat_lang_rect.x, chat_lang_rect.y + 52 + (_index - chat_lang_scroll) * 34, chat_lang_rect.width, 34)
						if _option_rect.collidepoint(event.pos):
							chat_display_lang = _code
							chat_lang_open = False
				elif mode == "Translator Mode" and sound_button_rect.collidepoint(event.pos):
					play_current()
				elif mode == "Translator Mode" and speed_button_rect.collidepoint(event.pos):
					speed_dropdown_open = not speed_dropdown_open
				elif mode == "Record Mode" and record_slowmo_rect.collidepoint(event.pos):
					record_slow_index = (record_slow_index + 1) % len(record_slow_options)
					listener.slow_factor = record_slow_options[record_slow_index]
				elif speed_dropdown_open:
					for index, option in enumerate(speed_options):
						option_rect = pygame.Rect(800, 322 + index * 38, 155, 38)
						if option_rect.collidepoint(event.pos):
							playback_speed = option
							speed_dropdown_open = False
				elif dropdown_rect.collidepoint(event.pos):
					dropdown_open = not dropdown_open
				elif dropdown_open:
					for index, option in enumerate(mode_options):
						option_rect = pygame.Rect(55, 322 + index * 46, 350, 46)
						if option_rect.collidepoint(event.pos):
							select_mode(option)
							dropdown_open = False
							current_code = ""
							press_started = None
							last_dot = None
							dot_emitted = False
			elif event.type == pygame.MOUSEWHEEL:
				if mode == "International Chat" and chat_lang_open:
					_visible = max(1, (720 - (chat_lang_rect.y + 52)) // 34)
					_max_scroll = max(0, len(CHAT_LANGUAGES) - _visible)
					chat_lang_scroll = min(_max_scroll, max(0, chat_lang_scroll - event.y))
			elif event.type == pygame.KEYDOWN:
				if event.key == pygame.K_ESCAPE:
					running = False
				elif event.key in (pygame.K_UP, pygame.K_DOWN):
					current_index = mode_options.index(mode)
					step = -1 if event.key == pygame.K_UP else 1
					select_mode(mode_options[(current_index + step) % len(mode_options)])
				elif mode == "Translator Mode" and event.key == pygame.K_BACKSPACE:
					translator_text = translator_text[:-1]
				elif mode == "Translator Mode" and event.key == pygame.K_DELETE:
					translator_text = ""
				elif event.key == pygame.K_TAB:
					show_help()
				elif mode == "International Chat" and chat_mode == "morse_to_word":
					if event.key in (pygame.K_PERIOD, pygame.K_MINUS):
						chat_input += "." if event.key == pygame.K_PERIOD else "-"
					elif event.key == pygame.K_SPACE:
						morse_space()
					elif event.key == pygame.K_SLASH:
						morse_slash()
					elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
						send_chat_message()
					elif event.key == pygame.K_BACKSPACE:
						chat_input = chat_input[:-1]
					elif event.key == pygame.K_DELETE:
						chat_input = ""
				elif mode == "International Chat" and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
					send_chat_message()
				elif mode == "International Chat" and event.key == pygame.K_BACKSPACE:
					chat_input = chat_input[:-1]
				elif mode == "International Chat" and event.key == pygame.K_DELETE:
					chat_input = ""
				elif event.key == pygame.K_DELETE:
					message = message.rstrip()
					message = message[:-1]
				elif event.key == pygame.K_BACKSPACE:
					message = ""
					current_code = ""
					last_signal = None
					press_started = None
					last_dot = None
					dot_emitted = False
				elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
					if mode == "Record Mode":
						listener.flush()
					if current_code:
						commit_letter()
					if message and not message.endswith(" "):
						message += " "
				elif mode == "Record Mode" and event.key == pygame.K_m:
					record_slow_index = (record_slow_index + 1) % len(record_slow_options)
					listener.slow_factor = record_slow_options[record_slow_index]
				elif mode == "Keyboard Buttons" and event.key in (pygame.K_PERIOD, pygame.K_MINUS):
					signal = "." if event.key == pygame.K_PERIOD else "-"
					record_signal(signal, now)
					play_signal(signal)
				elif mode not in ("Keyboard Buttons", "Translator Mode", "International Chat") and event.key == pygame.K_SPACE and press_started is None:
					press_started = now
					last_dot = now
					dot_emitted = False
			elif event.type == pygame.TEXTINPUT:
				if mode == "Translator Mode":
					translator_text += event.text
				elif mode == "International Chat" and chat_mode != "morse_to_word":
					chat_input += event.text
			elif event.type == pygame.KEYUP and event.key == pygame.K_SPACE and mode not in ("Translator Mode", "International Chat"):
				if press_started is not None:
					if mode == "Duration Mode":
						signal = "-" if now - press_started >= dash_threshold else "."
						record_signal(signal, now)
						play_signal(signal)
					elif not dot_emitted:
						record_signal("-", now)
						play_signal("-")
					press_started = None
					last_dot = None
					dot_emitted = False

		if mode == "Dot Stream Mode" and press_started is not None:
			while last_dot is not None and now - last_dot >= dot_interval:
				record_signal(".", last_dot + dot_interval)
				play_signal(".")
				last_dot += dot_interval
				dot_emitted = True

		if mode == "Record Mode":
			while not listener.out_queue.empty():
				decoded = listener.out_queue.get()
				if decoded == " ":
					if message and not message.endswith(" "):
						message += " "
				else:
					message += decoded

		if mode == "International Chat" and chat_client is not None:
			while not chat_client.inbox.empty():
				add_chat_message(chat_client.inbox.get())

		while now - last_check >= checker_interval:
			last_check += checker_interval
			check_pattern(last_check)

		if mode == "International Chat":
			draw_chat_screen(now)
			pygame.display.flip()
			update_help()
			clock.tick(120)
			continue

		screen.fill(background)
		pygame.draw.rect(screen, (15, 30, 40), (0, 0, 1200, 180))
		screen.blit(title_font.render("MORSE MACHINE", True, text_color), (55, 38))
		screen.blit(font.render("A tactile space-bar transmitter", True, accent), (58, 105))
		if mode == "Duration Mode":
			instructions = "Sharp tap (<180ms) = DOT  |  Hold (180-500ms) = DASH"
		elif mode == "Dot Stream Mode":
			instructions = "Tap SPACE for a dash  |  Hold SPACE for repeating dots"
		elif mode == "Translator Mode":
			instructions = "Type a word or phrase to see its Morse translation"
		elif mode == "Record Mode":
			instructions = "Point your mic at Morse beeps  |  M toggles slow-mo  |  Enter forces letter"
		else:
			instructions = "Press . for a dot  |  Press - for a dash"
		screen.blit(font.render(instructions, True, text_color), (58, 140))
		if mode == "Record Mode":
			if listener.is_speech:
				mic_status = "SPEECH DETECTED - IGNORING"
			elif listener.signal_active:
				mic_status = "TONE"
			else:
				mic_status = "LISTENING"
			screen.blit(font.render(
				f"SLOW ×{listener.slow_factor:g}  ·  {mic_status}  ·  dot {listener.dot_ms:.0f}ms  ·  dash {listener.dash_ms:.0f}ms",
				True, muted_text,
			), (58, 174))
			screen.blit(font.render(
				f"gap {listener.gap_ms:.0f}ms  ·  unit {listener.unit_ms:.0f}ms  ·  split {listener._split_ms[0]:.0f}ms",
				True, muted_text,
			), (58, 174 + 26))
		else:
			screen.blit(font.render(f"Pause {letter_gap}ms for the next letter  |  {word_gap}ms for a space", True, muted_text), (58, 174))

		pygame.draw.rect(screen, panel, (35, 215, 1130, 145), border_radius=12)
		screen.blit(label_font.render("INPUT MODE", True, accent), (55, 232))
		pygame.draw.rect(screen, panel_highlight, dropdown_rect, border_radius=8)
		screen.blit(font.render(mode, True, text_color), (73, 280))
		screen.blit(font.render("v", True, accent), (375, 280))
		screen.blit(font.render("Backspace deletes  |  Esc quits", True, muted_text), (455, 280))
		screen.blit(font.render("Tab opens the Morse list", True, muted_text), (455, 315))
		if mode == "Translator Mode":
			pygame.draw.rect(screen, accent_soft, sound_button_rect, border_radius=8)
			screen.blit(font.render("SOUND", True, text_color), (990, 280))
			pygame.draw.rect(screen, panel_highlight, speed_button_rect, border_radius=8)
			screen.blit(font.render("|  v", True, text_color), (940, 280))
		elif mode == "Record Mode":
			pygame.draw.rect(screen, accent_soft, record_slowmo_rect, border_radius=8)
			screen.blit(font.render(f"SLOW-MO ×{listener.slow_factor:g}", True, text_color), (802, 280))

		pygame.draw.rect(screen, panel, (35, 390, 535, 285), border_radius=12)
		pygame.draw.rect(screen, panel, (600, 390, 565, 285), border_radius=12)
		left_title = "TRANSLATOR INPUT" if mode == "Translator Mode" else "CURRENT MORSE"
		right_title = "MORSE TRANSLATION" if mode == "Translator Mode" else "MESSAGE"
		screen.blit(label_font.render(left_title, True, accent), (60, 420))
		screen.blit(label_font.render(right_title, True, accent), (625, 420))
		cursor = "|" if (now // 500) % 2 == 0 else " "
		if mode == "Translator Mode":
			draw_message(translator_text, pygame.Rect(60, 472, 470, 165))
		else:
			preview_code = listener.partial_code if mode == "Record Mode" else current_code
			if press_started is not None and mode == "Duration Mode":
				preview_code += "-" if now - press_started >= dash_threshold else "."
			draw_morse(preview_code, pygame.Rect(60, 472, 470, 100), bool(cursor.strip()))
		if mode == "Translator Mode":
			draw_translation(translator_text, pygame.Rect(625, 462, 500, 180))
			prediction_text = "TYPE TO TRANSLATE"
			prediction_label = "LETTER PREDICTION"
		else:
			partial = listener.partial_code if mode == "Record Mode" else current_code
			if not partial and mode == "Record Mode":
				prediction_text = "Listening..."
				prediction_label = "WORD PREDICTION"
			else:
				# Predict the word currently being formed: the committed
				# letters of the current word plus the letter being pressed.
				word_so_far = ""
				if message and not message.endswith(" "):
					word_so_far = message.split()[-1]
				predicted_words = _predict_words(partial, word_so_far)
				if predicted_words:
					prediction_text = " / ".join(predicted_words)
					prediction_label = "WORD PREDICTION"
				else:
					letter_predictions = predict_letters(partial)
					if letter_predictions:
						prediction_text = " / ".join(letter_predictions)
						prediction_label = "LETTER PREDICTION"
					elif partial:
						prediction_text = "Word: " + decode_obvious(partial)
						prediction_label = "LETTER PREDICTION"
					else:
						prediction_text = ""
						prediction_label = "LETTER PREDICTION"
		screen.blit(font.render(prediction_label, True, muted_text), (60, 585))
		screen.blit(font.render(prediction_text, True, text_color), (60, 612))
		if mode != "Translator Mode":
			draw_message(message, pygame.Rect(625, 472, 500, 165))
		if mode == "Record Mode":
			status = "SIGNAL" if listener.signal_active else "LISTENING"
			status_color = (242, 186, 73) if listener.signal_active else accent
		else:
			status = "RECORDING" if press_started is not None else "READY"
			status_color = accent if press_started is None else (242, 186, 73)
		screen.blit(font.render(status, True, status_color), (455, 645))
		if dropdown_open:
			for index, option in enumerate(mode_options):
				option_rect = pygame.Rect(55, 322 + index * 46, 350, 46)
				pygame.draw.rect(screen, panel_highlight, option_rect)
				screen.blit(font.render(option, True, text_color), (73, 330 + index * 46))
		if speed_dropdown_open and mode == "Translator Mode":
			for index, option in enumerate(speed_options):
				option_rect = pygame.Rect(800, 322 + index * 38, 155, 38)
				pygame.draw.rect(screen, panel_highlight, option_rect)
				screen.blit(font.render(f"{option}x", True, text_color), (815, 328 + index * 38))
		pygame.display.flip()
		update_help()
		clock.tick(120)

	if help_root is not None:
		help_root.destroy()
	if chat_client is not None:
		chat_client.disconnect()
	listener.stop()
	pygame.quit()


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser(description="Morse Machine — international Morse chat")
	parser.add_argument("--server", default=DEFAULT_CHAT_HOST, help="international chat server host")
	parser.add_argument("--port", type=int, default=DEFAULT_CHAT_PORT, help="international chat server port")
	parser.add_argument("--nick", default=DEFAULT_CHAT_NICK, help="your display name in the chat")
	parser.add_argument("--lang", default="en", help="your chat display language (ISO code, e.g. pt, es, fr)")
	parser.add_argument("--connect", action="store_true", help="open directly on International Chat")
	args = parser.parse_args()
	run_machine({
		"server": args.server,
		"port": args.port,
		"nick": args.nick,
		"lang": args.lang,
		"connect": args.connect,
	})
