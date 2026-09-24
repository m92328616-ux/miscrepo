"""Tests for the Morse-to-word prediction system.

Run with:

	python3 -m unittest test_morse -v
"""

import time
import unittest
from unittest import mock

import morse


def encode_word(word):
	return "".join(morse.MORSE_CODE[char] for char in word)


class DecodeCorrectnessTests(unittest.TestCase):
	"""Criterion: Morse input consistently produces the correct decoded letters."""

	def test_every_single_character_decodes(self):
		for character, code in morse.MORSE_CODE.items():
			self.assertEqual(morse.decode_obvious(code), character, code)
			self.assertEqual(morse.decode(code), character, code)

	def test_words_decode(self):
		self.assertEqual(morse.decode(".... . .-.. .-.. ---"), "HELLO")
		self.assertEqual(morse.decode(".... . .-.. .-.. --- / .-- --- .-. .-.. -.."), "HELLO WORLD")
		self.assertEqual(morse.decode("... --- ..."), "SOS")

	def test_continuous_word_run_decodes_to_word(self):
		self.assertEqual(morse.decode_obvious(encode_word("HELLO")), "HELLO")
		self.assertEqual(morse.decode_obvious(encode_word("HELP")), "HELP")
		self.assertEqual(morse.decode_obvious(encode_word("MORSE")), "MORSE")

	def test_space_separated_runs_not_merged(self):
		# ".... ." must decode as two letters, not be joined into "....." = 5
		self.assertEqual(morse.decode_obvious(".... ."), "HE")
		self.assertEqual(morse.decode(".... ."), "HE")

	def test_numbers_decode(self):
		self.assertEqual(morse.decode_obvious("....."), "5")
		self.assertEqual(morse.decode_obvious("....-"), "4")
		self.assertEqual(morse.decode_obvious("-----"), "0")


class InvalidInputTests(unittest.TestCase):
	"""Criterion: Invalid or incomplete Morse input is handled gracefully."""

	def test_garbage_returns_question_mark(self):
		self.assertEqual(morse.decode_obvious("???"), "?")
		# Two unrecognisable runs produce a "?" for each.
		self.assertEqual(morse.decode_obvious("not morse"), "??")

	def test_empty_input_is_safe(self):
		self.assertEqual(morse.decode_obvious(""), "")
		self.assertEqual(morse.decode_obvious("   "), "")
		self.assertEqual(morse.decode(""), "")

	def test_partial_run_does_not_crash_prediction(self):
		for partial in (".....-", "----.--", "..-..-", "-...-.-", ".--.--.-"):
			result = morse._predict_words(partial)
			self.assertIsInstance(result, tuple)
			for word in result:
				self.assertIsInstance(word, str)

	def test_incomplete_runs_return_something_graceful(self):
		# A valid-but-unfinished run should still give *some* answer.
		for partial in (".", "-", "....", "-.-."):
			decoded = morse.decode_obvious(partial)
			self.assertNotIn("?", decoded)


class WordPredictionTests(unittest.TestCase):
	"""Criterion: Word predictions are accurate and relevant, and common
	words are prioritised when several predictions are possible."""

	def test_predictions_never_cut_across_a_letter(self):
		# ... = S/H/V in progress; IS starts with I = "..", which does not
		# match a run of three dots.  Old code wrongly suggested IS.
		for word in morse._predict_words("..."):
			self.assertTrue(morse.MORSE_CODE[word[0]].startswith("..."), word)

	def test_complete_letter_takes_priority(self):
		# "...." is a completed H, so suggestions must start with H.
		words = morse._predict_words("....")
		self.assertTrue(words)
		for word in words:
			self.assertEqual(word[0], "H", word)

	def test_common_words_ranked_first(self):
		# I-words are all matches for ".."; the most common should win.
		words = morse._predict_words("..")
		self.assertIn("IN", words)
		self.assertLess(words.index("IN"), words.index("FOR") if "FOR" in words else len(words))
		for word in words:
			self.assertTrue(morse.MORSE_CODE[word[0]].startswith(".."), word)

	def test_context_of_committed_letters_is_used(self):
		# After committing H + E, typing L ("'.-..") should predict HEL* words.
		words = morse._predict_words(".-..", context="HE")
		self.assertIn("HELP", words)
		self.assertIn("HELLO", words)

	def test_prediction_updates_as_user_keeps_entering(self):
		# Typing HELLO letter by letter narrows the prediction each step.
		self.assertIn("HE", morse._predict_words(".", context="H"))
		self.assertIn("HELP", morse._predict_words(".-..", context="HE"))
		self.assertIn("HELLO", morse._predict_words("---", context="HELL"))

	def test_word_boundary_resets_context(self):
		# After a completed word, suggestions start fresh with the run.
		words = morse._predict_words("-", context="")
		for word in words:
			self.assertTrue(morse.MORSE_CODE[word[0]].startswith("-"), word)

	def test_number_completion_not_treated_as_word(self):
		# "....." is the digit 5; there is no word to predict for it.
		self.assertEqual(morse._predict_words("....."), ())

	def test_exact_single_letter_words_suggested(self):
		words = morse._predict_words("-")
		self.assertIn("THE", words)


class LetterPredictionTests(unittest.TestCase):
	"""Criterion: Incomplete Morse sequences are handled and the closest
	character is listed first."""

	def test_empty_prefix_starts_the_tree(self):
		self.assertEqual(morse.predict_letters(""), ("E", "T"))

	def test_exact_match_first(self):
		self.assertEqual(morse.predict_letters(".")[0], "E")
		self.assertEqual(morse.predict_letters("-")[0], "T")
		self.assertEqual(morse.predict_letters("..")[0], "I")
		self.assertEqual(morse.predict_letters("....")[0], "H")

	def test_completed_numbers_are_suggested(self):
		self.assertEqual(morse.predict_letters("....-"), ("4",))
		self.assertEqual(morse.predict_letters("....."), ("5",))
		self.assertEqual(morse.predict_letters("..---"), ("2",))

	def test_prefixes_are_respected(self):
		for prefix in (".", "-", ".-", "-.", "...", "..-"):
			for char in morse.predict_letters(prefix):
				self.assertTrue(morse.MORSE_CODE[char].startswith(prefix), char)


class SpaceAndBoundaryTests(unittest.TestCase):
	"""Criterion: Spaces and word boundaries work as expected."""

	def test_decode_multiple_words(self):
		self.assertEqual(morse.decode(".... . / -.-- --- ..-"), "HE YOU")

	def test_decode_with_stray_slashes_and_spaces(self):
		self.assertEqual(morse.decode("  .... .   /  .--   "), "HE W")

	def test_decode_timed_word_boundaries(self):
		# H = ...., E = ., T = -  (letters separated by 420-999ms gaps)
		signals = [(".", 0), (".", 100), (".", 200), (".", 300)]  # H
		signals.append((".", 800))                                 # gap 500 -> H committed, E starts
		signals.append(("-", 1300))                                # gap 500 -> E committed, T starts
		self.assertEqual(morse.decode_timed(signals), "HET")

	def test_decode_timed_word_space(self):
		# M = --, A = .-, then a >=1000ms gap inserts a space before E = .
		signals = [("-", 0), ("-", 80)]              # M
		signals.append((".", 600))                   # gap 520 -> M committed, A starts
		signals.append(("-", 700))                   # completes A
		self.assertEqual(morse.decode_timed(signals), "MA")
		signals.append((".", 1800))  # gap 1100 >= 1000 -> A committed + space, E starts
		self.assertEqual(morse.decode_timed(signals), "MA E")


class ChatConversionTests(unittest.TestCase):
	"""Criterion (issue #2): Morse-to-Word and Words-to-Morse chat output
	must show the payload, never a stray boolean/status value."""

	def test_morse_to_word_body_keeps_morse_and_notes_translation(self):
		lines, note = morse.chat_rendering(".... . .-.. .-.. ---", "HELLO")
		self.assertEqual(lines, [".... . .-.. .-.. ---"])
		self.assertEqual(note, "-> HELLO")

	def test_words_to_morse_round_trip(self):
		self.assertEqual(
			morse.encode_words_to_morse("hello world"),
			".... . .-.. .-.. --- / .-- --- .-. .-.. -..",
		)
		self.assertEqual(
			morse.decode_morse_entry(morse.encode_words_to_morse("HELLO WORLD")),
			"HELLO WORLD",
		)

	def test_plain_text_translation_has_no_note(self):
		lines, note = morse.chat_rendering(None, "HOLA")
		self.assertEqual(lines, ["HOLA"])
		self.assertIsNone(note)

	def test_boolean_flag_never_renders_as_True(self):
		# Regression: the old submit_translation leaked the boolean flag into
		# wrap_chat, showing "True" as the message body.
		for stray in (True, False, 1, 0):
			lines, note = morse.chat_rendering(stray, "PAYLOAD")
			for line in lines:
				self.assertNotEqual(line.strip(), "True", pstring := str(stray))
				self.assertNotIn("True", line)
			self.assertEqual(lines, ["PAYLOAD"])
			self.assertIsNone(note)

	def test_chat_entry_body_is_never_True(self):
		# Simulate the full submit path: the morse payload is stored verbatim,
		# and the translation only fills the note.
		morse_text = "... --- ..."
		lines, note = morse.chat_rendering(morse_text, "SOS")
		body = " ".join(lines)
		self.assertNotIn("True", body)
		self.assertTrue(body.strip().endswith("..."))
		self.assertEqual(note, "-> SOS")


class ChatWrapperTests(unittest.TestCase):
	"""Criterion: the 1080px chat wrapping keeps messages intact."""

	def test_wrap_chat_splits_long_messages_into_lines(self):
		long_word = " ".join("totallybrokenmorse" for _ in range(40))
		lines = morse._wrap_chat(long_word)
		self.assertGreater(len(lines), 1)
		self.assertEqual(" ".join(lines).split(), long_word.split())

	def test_wrap_chat_single_short_line(self):
		self.assertEqual(morse._wrap_chat("HELLO"), ["HELLO"])

	def test_wrap_chat_empty_input_returns_placeholder(self):
		self.assertEqual(morse._wrap_chat(""), [" "])

	def test_wrap_chat_takes_custom_measure(self):
		lines = morse._wrap_chat("A B C", measure=lambda candidate: len(candidate) * 1000)
		self.assertEqual(" ".join(lines), "A B C")
		self.assertGreaterEqual(len(lines), 1)

	def test_wrap_chat_respects_max_width(self):
		lines = morse._wrap_chat(
			"HELLO WORLD SPLIT HERE",
			measure=lambda candidate: len(candidate) * 20,
			max_width=100,
		)
		self.assertTrue(lines)
		for line in lines:
			self.assertLessEqual(len(line) * 20, 100)


class GoogleTranslateTargetTests(unittest.TestCase):
	"""Criterion (issue #3): the selected language is the translation target,
	the source language is auto-detected, and supported languages translate
	into the currently selected language.

	The public Google endpoint is mocked so the tests run offline. The mock
	answers the same way translate.googleapis.com does: the first element of
	each ``[[translated, source, ...], ...]`` chunk is the translated text.
	"""

	def setUp(self):
		morse._translate_cached.cache_clear()

	@staticmethod
	def _patch_urlopen(table):
		def fake_open(request, timeout=None):
			from urllib.parse import parse_qs, urlparse
			query = parse_qs(urlparse(request.full_url).query)
			source = query.get("sl", ["?"])[0]
			target = query.get("tl", ["?"])[0]
			text = query.get("q", [""])[0]
			translated = table.get((source, target, text), text)
			payload = [[[translated, source, None, None]], None, source, None]
			body = __import__("json").dumps(payload).encode("utf-8")
			return mock.MagicMock(
				__enter__=lambda self: self,
				__exit__=lambda *args: False,
				read=lambda: body,
			)
		return mock.patch.object(
			morse.urllib.request, "urlopen", side_effect=fake_open, autospec=True
		)

	def test_english_to_russian(self):
		table = {("auto", "ru", "hello world"): "привет мир"}
		with self._patch_urlopen(table):
			self.assertEqual(morse.google_translate("hello world", "ru"), "привет мир")

	def test_german_to_russian(self):
		table = {("auto", "ru", "guten tag"): "добрый день"}
		with self._patch_urlopen(table):
			self.assertEqual(morse.google_translate("guten tag", "ru"), "добрый день")

	def test_french_to_russian(self):
		table = {("auto", "ru", "bonjour"): "привет"}
		with self._patch_urlopen(table):
			self.assertEqual(morse.google_translate("bonjour", "ru"), "привет")

	def test_spanish_to_russian(self):
		table = {("auto", "ru", "hola"): "привет"}
		with self._patch_urlopen(table):
			self.assertEqual(morse.google_translate("hola", "ru"), "привет")

	def test_japanese_to_russian(self):
		table = {("auto", "ru", "こんにちは"): "привет"}
		with self._patch_urlopen(table):
			self.assertEqual(morse.google_translate("こんにちは", "ru"), "привет")

	def test_supported_sources_all_translate_into_russian(self):
		samples = {
			"auto": {
				"hello": "привет",
				"guten tag": "добрый день",
				"bonjour": "привет",
				"hola": "привет",
				"こんにちは": "привет",
				"привет": "привет",
			}
		}
		table = {("auto", "ru", text): out for text, out in samples["auto"].items()}
		with self._patch_urlopen(table):
			for source_text, russian in samples["auto"].items():
				self.assertEqual(morse.google_translate(source_text, "ru"), russian, source_text)

	def test_russian_to_english_when_target_changes(self):
		table = {("auto", "en", "привет мир"): "hello world"}
		with self._patch_urlopen(table):
			self.assertEqual(morse.google_translate("привет мир", "en"), "hello world")

	def test_german_and_russian_into_english(self):
		table = {
			("auto", "en", "guten tag"): "good day",
			("auto", "en", "привет мир"): "hello world",
		}
		with self._patch_urlopen(table):
			self.assertEqual(morse.google_translate("guten tag", "en"), "good day")
			self.assertEqual(morse.google_translate("привет мир", "en"), "hello world")

	def test_target_language_is_sent_to_endpoint(self):
		seen = []

		def fake_open(request, timeout=None):
			from urllib.parse import parse_qs, urlparse
			seen.append(parse_qs(urlparse(request.full_url).query))
			return mock.MagicMock(
				__enter__=lambda self: self,
				__exit__=lambda *args: False,
				read=lambda: b'[[["out","auto",null,null]],null,"auto",null]',
			)

		with mock.patch.object(morse.urllib.request, "urlopen", side_effect=fake_open):
			morse.google_translate("текст", "de")
		self.assertEqual(seen[-1]["tl"], ["de"])
		self.assertEqual(seen[-1]["sl"], ["auto"])

	def test_failed_translation_returns_original_text(self):
		with mock.patch.object(morse.urllib.request, "urlopen", side_effect=OSError("offline")):
			self.assertEqual(morse.google_translate("hello world", "ru"), "hello world")

	def test_empty_input_and_target_are_safe(self):
		self.assertEqual(morse.google_translate("", "ru"), "")
		self.assertEqual(morse.google_translate("hello", ""), "hello")
		self.assertEqual(morse.google_translate(None, "ru"), None)

	def test_falls_back_to_next_client_when_first_is_rate_limited(self):
		class _RateLimited(OSError):
			pass

		calls = []

		def fake_open(request, timeout=None):
			calls.append(request.full_url)
			if len(calls) == 1:
				raise _RateLimited(429, "Too Many Requests")
			return mock.MagicMock(
				__enter__=lambda self: self,
				__exit__=lambda *args: False,
				read=lambda: '[[["привет мир","hello world",null,null,10]],null,"en",null]'.encode("utf-8"),
			)

		with mock.patch.object(morse.urllib.request, "urlopen", side_effect=fake_open):
			self.assertEqual(morse.google_translate("hello world", "ru"), "привет мир")
		self.assertGreaterEqual(len(calls), 2)

	def test_returns_original_text_when_every_client_fails(self):
		def fake_open(request, timeout=None):
			raise OSError(503, "Service Unavailable")

		with mock.patch.object(morse.urllib.request, "urlopen", side_effect=fake_open):
			self.assertEqual(morse.google_translate("hello world", "ru"), "hello world")


class TranslatorWorkerTargetTests(unittest.TestCase):
	"""Criterion (issue #3): the background worker translates messages into
	the target language the caller selected, on a background thread."""

	def test_worker_submits_selected_language_as_target(self):
		seen = {}

		def fake_google(text, target, source="auto"):
			seen["text"] = text
			seen["target"] = target
			seen["source"] = source
			return "TRANSLATED"

		with mock.patch.object(morse, "google_translate", side_effect=fake_google):
			worker = morse._Translator()
			received = []
			worker.submit(received.append, "hola", "ru")
			deadline = time.time() + 3
			while not received and time.time() < deadline:
				time.sleep(0.02)
			self.assertEqual(received, ["TRANSLATED"])
		self.assertEqual(seen["text"], "hola")
		self.assertEqual(seen["target"], "ru")
		self.assertEqual(seen["source"], "auto")

	def test_worker_uses_auto_source_detection(self):
		seen = {}

		def fake_google(text, target, source="auto"):
			seen["source"] = source
			return text

		with mock.patch.object(morse, "google_translate", side_effect=fake_google):
			worker = morse._Translator()
			done = []
			worker.submit(done.append, "texto", "es")
			deadline = time.time() + 3
			while not done and time.time() < deadline:
				time.sleep(0.02)
		self.assertEqual(seen["source"], "auto")


class EncodeRobustnessTests(unittest.TestCase):
	"""Criterion (issue #3): foreign-script input (e.g. Russian) must never
	crash the Morse encoder, which is now fed by the translator mode."""

	def test_encode_skips_unsupported_characters(self):
		self.assertEqual(morse.encode("Привет мир"), "")
		self.assertEqual(morse.encode("Guten Tag!"), "--. ..- - . -. / - .- --.")

	def test_encode_still_round_trips_latin(self):
		self.assertEqual(
			morse.encode("hello world"),
			".... . .-.. .-.. --- / .-- --- .-. .-.. -..",
		)


if __name__ == "__main__":
	unittest.main()