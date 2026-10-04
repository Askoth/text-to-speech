# Project Guidelines

## Language: English (enforcement)

This repo was forked from a project that mixed Italian and English. The standard for all
new and touched code is **English**. Apply it to:

- Code identifiers (functions, classes, methods, variables, constants, params, modules)
- File names (`.py`) and test names
- Comments and docstrings
- Terminal/CLI output messages (`info` / `warn` / `error` / `print`)

### Out of scope — do NOT translate

- `src/translations.py` — the `"it"` / `"en"` i18n strings are product content, keep as-is
- Any `.it` / `README.it.md` docs
- TTS input text and user-provided data
- Third-party / upstream content we do not own

### Rule for future work

- New code ships in English from day one — identifiers, file names, comments, docstrings, CLI output.
- Existing Italian is migrated only as a byproduct of touching a file: fix identifiers in that file,
  update all references, keep the test suite green. Do not launch a blanket translation pass.

---

## Migration Plan (existing code — do incrementally, not one big-bang)

This is a plan, not a task to execute now. Pick one slice, land it green, move to the next.

### 1. File renames

| Current | Target | Notes |
|---------|--------|-------|
| `src/leggi.py` | `src/reader.py` | CLI entry, `main()` lives here |
| `leggi.py` (root wrapper) | `reader.py` | thin shim, update `from src.leggi import main` → `from src.reader import main` |
| `tests/test_leggi.py` | `tests/test_reader.py` | keep test names meaningful; see below |

`app.py`, `config.py`, `synthesis.py`, `converters.py`, `tts_engine.py`, `translations.py`
already have English names — no rename.

### 2. Identifier renames (public API)

| Current | Target |
|---------|--------|
| `leggi_con_piper` | `read_with_piper` |
| `scarica_voce_piper` | `download_piper_voice` |
| `sintetizza_piper` | `synthesize_piper` |
| `verifica_prerequisiti` | `check_prerequisites` |
| `suggerisci_installazione` | `suggest_installation` |
| `calcola_path_output` | `calc_output_path` |
| `concatena_wav` | `concat_wav` |
| `concatena_mp3` | `concat_mp3` |
| `wav_a_mp3` | `wav_to_mp3` |
| `file_a_testo` | `file_to_text` |
| `riproduci_audio` | `play_audio` |
| `mostra_paragrafo` | `show_paragraph` |
| `_trova_player` | `_find_player` |
| `_ha_player` | `_has_player` |
| `_riproduci_async` | `_play_async` |
| `_converti_*` (docx/epub/html/markdown/pdf/testo) | `_convert_*` |

### 3. CLI output

Move `info` / `warn` / `error` / `print` payloads in `config.py`, `leggi.py`, `synthesis.py`,
`app.py` to English. Keep the terminal color/format helpers unchanged.

### 4. Docs & metadata (later)

- `src/__init__.py` docstring, root `app.py` / `leggi.py` docstrings, module headers.
- `CHANGELOG.md` and `SECURITY.md` (the non-`.it` variants).
- `pyproject.toml` `description` placeholder.

### Safety / process

- One slice per PR; run `uv run pytest` and `uv run ruff check` before committing.
- Grep for each old name before committing to make sure no stale references remain.
- Keep behavior identical; the only allowed diff is language.
- `src/translations.py` stays untouched (product content).
