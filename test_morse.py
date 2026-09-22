"""Tests for the Morse-to-word prediction system.

Run with:

	python3 -m unittest test_morse -v
"""

import unittest

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


if __name__ == "__main__":
	unittest.main()