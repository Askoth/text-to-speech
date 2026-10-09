"""GUI i18n — Italian/English strings ported from ``static/i18n.js``.

This is program data (shipped with the app), not user config — the only
i18n-adjacent *config* is the language *selection*, which lives in
``settings.toml`` and is fed in here once at startup. There is no in-app
switcher: :func:`set_lang` is called a single time by the app bootstrap
(T6), defaulting to :data:`DEFAULT_LANG` ("en") until then. The tables mirror
``i18n.js`` 1:1 minus the unused ``style`` keys, and this module is Qt-free so
it can be imported/tested without PyQt5.
"""

DEFAULT_LANG = "en"
_LANGS = ("en", "it")

TRANSLATIONS = {
    "it": {
        # Toolbar
        "toolbar.chooseFile": "Scegli file",
        "toolbar.chooseFileAria": "Scegli file da leggere",
        "toolbar.voice": "Voce",
        "toolbar.voiceAria": "Selezione voce",
        "toolbar.loading": "Caricamento...",
        "toolbar.saveBtn": "Salva MP3",
        "toolbar.saveAria": "Scarica audio completo",
        "toolbar.saveTitle": "Scarica l'intero testo come MP3",
        # Empty state
        "empty.title": "Carica un file per iniziare",
        "empty.formats": "MD, TXT, EPUB, DOCX, HTML, PDF",
        # Error banner
        "error.closeAria": "Chiudi messaggio di errore",
        # Progress
        "progress.aria": "Avanzamento lettura",
        "progress.sliderTitle": "Clicca per saltare a un punto del testo",
        "progress.counter": "Paragrafo {current} / {total}",
        "progress.counterEmpty": "Paragrafo — / —",
        "progress.valueText": "Paragrafo {current} di {total}",
        # Player controls
        "player.controlsAria": "Controlli riproduzione",
        "player.startAria": "Torna all'inizio",
        "player.startTitle": "Vai al primo paragrafo",
        "player.prevAria": "Paragrafo precedente",
        "player.prevTitle": "Paragrafo precedente (freccia sinistra)",
        "player.playAria": "Riproduci",
        "player.pauseAria": "Pausa",
        "player.playTitle": "Riproduci / Pausa (Spazio)",
        "player.loadingAria": "Caricamento audio...",
        "player.stopAria": "Stop",
        "player.stopTitle": "Stop e torna al primo paragrafo",
        "player.nextAria": "Paragrafo successivo",
        "player.nextTitle": "Paragrafo successivo (freccia destra)",
        "player.repeatAria": "Ripeti paragrafo",
        "player.repeatTitle": "Ripeti paragrafo corrente (R)",
        # Control labels
        "label.start": "Inizio",
        "label.prev": "Prec.",
        "label.playPause": "Play / Pausa",
        "label.stop": "Stop",
        "label.next": "Succ.",
        "label.repeat": "Ripeti",
        # Keyboard hints
        "kbd.space": "Spazio",
        "kbd.playPause": "Play/Pausa",
        "kbd.prev": "Precedente",
        "kbd.next": "Successivo",
        "kbd.repeat": "Ripeti",
        "kbd.aria": "Scorciatoie da tastiera disponibili",
        # Dynamic messages
        "msg.loadError": "Errore nel caricamento del file.",
        "msg.loadErrorDetail": "Errore nel caricamento: {message}",
        "msg.synthesisError": "Errore sintesi audio.",
        "msg.synthesisErrorDetail": "Errore sintesi: {message} Riprova o cambia voce.",
        "msg.playbackError": "Errore di riproduzione audio. Riprova o cambia voce.",
        "msg.saveFailed": "Salvataggio fallito: {message}",
    },
    "en": {
        # Toolbar
        "toolbar.chooseFile": "Choose file",
        "toolbar.chooseFileAria": "Choose a file to read",
        "toolbar.voice": "Voice",
        "toolbar.voiceAria": "Voice selection",
        "toolbar.loading": "Loading...",
        "toolbar.saveBtn": "Save MP3",
        "toolbar.saveAria": "Download full audio",
        "toolbar.saveTitle": "Download the entire text as MP3",
        # Empty state
        "empty.title": "Load a file to start",
        "empty.formats": "MD, TXT, EPUB, DOCX, HTML, PDF",
        # Error banner
        "error.closeAria": "Close error message",
        # Progress
        "progress.aria": "Reading progress",
        "progress.sliderTitle": "Click to jump to a point in the text",
        "progress.counter": "Paragraph {current} / {total}",
        "progress.counterEmpty": "Paragraph — / —",
        "progress.valueText": "Paragraph {current} of {total}",
        # Player controls
        "player.controlsAria": "Playback controls",
        "player.startAria": "Go to beginning",
        "player.startTitle": "Go to first paragraph",
        "player.prevAria": "Previous paragraph",
        "player.prevTitle": "Previous paragraph (left arrow)",
        "player.playAria": "Play",
        "player.pauseAria": "Pause",
        "player.playTitle": "Play / Pause (Space)",
        "player.loadingAria": "Loading audio...",
        "player.stopAria": "Stop",
        "player.stopTitle": "Stop and go to first paragraph",
        "player.nextAria": "Next paragraph",
        "player.nextTitle": "Next paragraph (right arrow)",
        "player.repeatAria": "Repeat paragraph",
        "player.repeatTitle": "Repeat current paragraph (R)",
        # Control labels
        "label.start": "Start",
        "label.prev": "Prev",
        "label.playPause": "Play / Pause",
        "label.stop": "Stop",
        "label.next": "Next",
        "label.repeat": "Repeat",
        # Keyboard hints
        "kbd.space": "Space",
        "kbd.playPause": "Play/Pause",
        "kbd.prev": "Previous",
        "kbd.next": "Next",
        "kbd.repeat": "Repeat",
        "kbd.aria": "Available keyboard shortcuts",
        # Dynamic messages
        "msg.loadError": "Error loading file.",
        "msg.loadErrorDetail": "Error loading: {message}",
        "msg.synthesisError": "Audio synthesis error.",
        "msg.synthesisErrorDetail": "Synthesis error: {message} Try again or change voice.",
        "msg.playbackError": "Audio playback error. Try again or change voice.",
        "msg.saveFailed": "Save failed: {message}",
    },
}

_current = DEFAULT_LANG


def current():
    """Return the active language code ('en' or 'it')."""
    return _current


def set_lang(lang):
    """Set the active language. Returns the code actually in effect.

    Called once at bootstrap from ``settings.toml``. Unknown, absent or
    non-string values normalize to :data:`DEFAULT_LANG` (the app warns +
    falls back rather than hard-failing; only the CLI ``validate`` is strict).
    """
    global _current
    try:
        lang = str(lang).strip().lower()
    except (TypeError, ValueError):
        lang = ""
    _current = lang if lang in TRANSLATIONS else DEFAULT_LANG
    return _current


class _SafeFormat(dict):
    """A format mapping that renders unknown placeholders as literal ``{key}``.

    Mirrors the JS contract (an unfilled ``{key}`` stays put) and keeps ``t``
    total — a missing param is a caller bug, not a reason to raise.
    """

    def __missing__(self, key):
        return f"{{{key}}}"


def t(key, **params):
    """Return ``key`` translated in the active language.

    Interpolates ``{current}`` / ``{total}`` / ``{message}`` from ``params``;
    a placeholder with no matching param is left as its literal ``{key}``.
    Falls back to :data:`DEFAULT_LANG` for a key missing in the active table,
    then to ``key`` itself (never returns ``None``).
    """
    text = TRANSLATIONS[_current].get(key)
    if text is None:
        text = TRANSLATIONS[DEFAULT_LANG].get(key, key)
    return text.format_map(_SafeFormat(params))
