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


def encode(text):
	"""Convert text to Morse, using / between words."""
	words = text.upper().split()
	return " / ".join(
		" ".join(MORSE_CODE[character] for character in word)
		for word in words
	)


def decode_obvious(morse):
	"""Choose the most likely word or letter split for a Morse run."""
	code = "".join(morse.split())
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
	"""Return likely letters whose reference-tree paths match a Morse prefix."""
	prefix = "".join(morse.split())
	if not prefix:
		return ("E", "T")
	candidates = [
		(character, code)
		for character, code in MORSE_CODE.items()
		if character.isalpha() and code.startswith(prefix)
	]
	candidates.sort(
		key=lambda item: (
			len(item[1]) - len(prefix),
			item[1].replace(".", "0").replace("-", "1"),
		)
	)
	return tuple(character for character, _ in candidates[:limit])


@lru_cache(maxsize=None)
def _predict_words(prefix):
	"""Predict the word being formed from a dot/dash run prefix.

	Uses the same vocabulary as the other modes (``_WORD_BY_MORSE``) and
	returns the most common words whose full Morse run begins with what has
	been heard so far.
	"""
	if not prefix:
		return ()
	matches = [
		(rank, word)
		for code, (rank, word) in _WORD_BY_MORSE.items()
		if code.startswith(prefix)
	]
	matches.sort(key=lambda item: (item[0], item[1]))
	return tuple(word for _, word in matches[:4])


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
	an adaptive, self-calibrating energy threshold (the "AI-assisted key
	detection": it tracks background noise and adapts to the sender's
	volume and speed instead of using a fixed cutoff), measures each key
	press as a dot or dash, and uses the gaps between presses to split
	letters and words.  Decoded characters are pushed to ``out_queue`` for
	the caller to drain.

	The most recent partial letter is exposed through :attr:`partial_code`,
	and whether a tone is currently being heard through :attr:`signal_active`.
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

	def start(self):
		"""Open the microphone and begin decoding in the background."""
		import threading
		import sounddevice as sd
		if self._running:
			return
		self._buffer = []
		self._running = True
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
		"""Duration of the most recent dot, stretched by slow-motion."""
		return self._last_dot_ms[0]

	@property
	def dash_ms(self):
		"""Duration of the most recent dash, stretched by slow-motion."""
		return self._last_dash_ms[0]

	@property
	def gap_ms(self):
		"""Most recent inter-key gap, stretched by slow-motion."""
		return self._last_gap_ms[0]

	@property
	def unit_ms(self):
		"""Calibrated dot-unit length, stretched by slow-motion."""
		return self._unit_ms[0]

	def _run(self):
		import numpy as np
		import time

		noise_floor = self.min_amp
		# Unit length (ms) used to tell dots and dashes apart; adapts to speed.
		unit_length = 90.0
		dot_times = []
		key_active = False
		confirm = 0
		key_start_samples = 0
		last_key_end_samples = None
		offset = 0

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
			if energy < noise_floor:
				noise_floor = max(self.min_amp, noise_floor * 0.9 + energy * 0.1)
			threshold = max(self.min_amp, noise_floor * self.noise_factor)
			now_samples = offset + self.chunk_size
			offset = now_samples
			stretch = self.slow_factor

			if not key_active:
				if energy >= threshold:
					confirm += 1
					if confirm >= 2:
						# A new word has begun: if the pause since the previous
						# letter was a word gap, the space belongs here.
						if self._pending_space[0]:
							gap_check = (
								(now_samples - last_key_end_samples)
								* 1000.0 / self.sample_rate * stretch / unit_length
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
						if last_key_end_samples is not None:
							gap_ms = (key_start_samples - last_key_end_samples) * 1000.0 / self.sample_rate * stretch
						else:
							gap_ms = 0.0
						last_key_end_samples = now_samples
						self._classify(duration_ms, gap_ms, unit_length, dot_times)
						# Re-estimate the unit length from recent dot durations.
						if len(dot_times) >= 4:
							fresh = dot_times[-8:]
							unit_length = sorted(fresh)[len(fresh) // 2]
							self._unit_ms[0] = unit_length
					# else still keyed on; keep waiting
				else:
					confirm = 0

			# Auto-commit the trailing letter after a quiet stretch so the
			# final letter of a transmission doesn't hang waiting for a key.
			# Only the letter is committed here; a word space is emitted by
			# the next key-down handler if the pause turns out to be a word
			# gap.  This keeps messages free of leading/trailing spaces.
			if not key_active and last_key_end_samples is not None:
				idle_units = (
					(now_samples - last_key_end_samples)
					* 1000.0 / self.sample_rate * stretch / unit_length
				)
				if idle_units >= 2.4 and self._partial[0]:
					self.out_queue.put(decode_obvious(self._partial[0]))
					self._partial[0] = ""
					self._pending_space[0] = True

	def _classify(self, duration_ms, gap_ms, unit_length, dot_times):
		if duration_ms <= 0:
			return
		# A dash is roughly 3 units; a dot is 1 unit.  Anything much longer
		# than a dash is treated as noise / a stuck key.
		if duration_ms >= unit_length * 2.2:
			signal = "-"
			self._last_dash_ms[0] = duration_ms
		elif duration_ms >= unit_length * 0.5:
			signal = "."
			dot_times.append(duration_ms)
			self._last_dot_ms[0] = duration_ms
		else:
			return
		self._last_gap_ms[0] = gap_ms

		# The gap sits BETWEEN the previous key and this one, so it only
		# closes the letter/word that came before — never the one starting now.
		previous = self._partial[0]
		if previous:
			if gap_ms >= unit_length * 4.4:
				self.out_queue.put(decode_obvious(previous))
				self.out_queue.put(" ")
				self._partial[0] = ""
			elif gap_ms >= unit_length * 2.2:
				self.out_queue.put(decode_obvious(previous))
				self._partial[0] = ""
		self._partial[0] = self._partial[0] + signal

	def flush(self):
		"""Commit the current partial letter without adding a trailing space."""
		if self._partial[0]:
			self.out_queue.put(decode_obvious(self._partial[0]))
			self._partial[0] = ""


def run_machine():
	"""Run a pygame Morse keyer controlled by the space bar."""
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
	mode_options = ("Duration Mode", "Dot Stream Mode", "Keyboard Buttons", "Translator Mode", "Record Mode")
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
		if not audio_enabled:
			return
		sounds = [dot_sound if symbol == "." else dash_sound for symbol in code if symbol in ".-"]
		if not sounds:
			return
		sound_channel.play(sounds[0])
		for sound in sounds[1:]:
			sound_channel.queue(sound)

	def play_signal(signal):
		if audio_enabled:
			(dot_sound if signal == "." else dash_sound).play()

	def play_current():
		if mode == "Translator Mode":
			morse_output = encode(translator_text)
		else:
			morse_output = encode(message)
		if audio_enabled and morse_output:
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
		nonlocal mode, current_code, press_started, last_dot, dot_emitted, last_signal
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
		for row, line in enumerate(lines):
			x_position = area.x
			y_position = area.y + row * line_height
			for character, code in line:
				label = translation_font.render(f"[{character}]", True, accent)
				pattern = morse_font.render(code, True, text_color)
				screen.blit(label, (x_position, y_position))
				screen.blit(pattern, (x_position, y_position + translation_font.get_linesize()))
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
		help_window.protocol("WM_DELETE_WINDOW", help_window.withdraw)
		help_window.bind("<Tab>", lambda _event: help_window.withdraw())

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

	while running:
		now = pygame.time.get_ticks()
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				running = False
			elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
				if mode == "Translator Mode" and sound_button_rect.collidepoint(event.pos):
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
				elif mode != "Keyboard Buttons" and event.key == pygame.K_SPACE and press_started is None:
					press_started = now
					last_dot = now
					dot_emitted = False
			elif event.type == pygame.TEXTINPUT and mode == "Translator Mode":
				translator_text += event.text
			elif event.type == pygame.KEYUP and event.key == pygame.K_SPACE:
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
			while now - last_dot >= dot_interval:
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

		while now - last_check >= checker_interval:
			last_check += checker_interval
			check_pattern(last_check)

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
			screen.blit(font.render(
				f"SLOW ×{listener.slow_factor:g}  ·  dot {listener.dot_ms:.0f}ms  ·  dash {listener.dash_ms:.0f}ms  ·  gap {listener.gap_ms:.0f}ms",
				True, muted_text,
			), (58, 174))
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
		else:
			if mode == "Record Mode":
				partial = listener.partial_code
				if not partial:
					prediction_text = "Listening..."
				else:
					# Same prediction system as the other modes: word runs
					# first, then individual letter candidates.
					predicted_words = _predict_words(partial)
					if predicted_words:
						prediction_text = " / ".join(predicted_words)
					else:
						letter_predictions = predict_letters(partial)
						if letter_predictions:
							prediction_text = " / ".join(letter_predictions)
						else:
							prediction_text = "Word: " + decode_obvious(partial)
			else:
				predictions = predict_letters(current_code)
				if predictions:
					prediction_text = " / ".join(predictions)
				else:
					prediction_text = "Word: " + decode_obvious(current_code)
		screen.blit(font.render("WORD PREDICTION" if mode == "Record Mode" else "LETTER PREDICTION", True, muted_text), (60, 585))
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
	listener.stop()
	pygame.quit()


if __name__ == "__main__":
	run_machine()
