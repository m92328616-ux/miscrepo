"""Morse Machine package.

Re-exports the symbols from ``morse/morse.py`` so the code works from the
repository root (``import morse``) as well as from inside the ``morse/``
directory.  The underscore-prefixed helpers the test-suite references are
re-exported explicitly because a wildcard import would skip them.
"""

from morse.morse import (  # noqa: F401  (intentional re-export)
	CHAT_LANGUAGES,
	DEFAULT_CHAT_HOST,
	DEFAULT_CHAT_PORT,
	DEFAULT_CHAT_NICK,
	LANGUAGE_BY_CODE,
	_Translator,
	MORSE_CODE,
	MorseChatClient,
	MorseListener,
	_predict_words,
	_script_of,
	_translate_cached,
	_wrap_chat,
	apply_translation,
	chat_rendering,
	decode,
	decode_morse_entry,
	decode_obvious,
	decode_steps,
	decode_timed,
	encode,
	encode_words_to_morse,
	get_font_stack,
	google_translate,
	predict_letters,
	run_machine,
	urllib,
)