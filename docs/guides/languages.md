# Language Support

OSINT-D2 supports 5 languages across the entire stack: CLI, web dashboard, AI analysis prompts, and PDF reports.

## Supported Languages

| Code | Language | Coverage |
|------|----------|----------|
| `en` | English | Full (CLI, UI, AI, PDF) |
| `es` | Spanish | Full (CLI, UI, AI, PDF) |
| `pt` | Portuguese | Full (CLI, UI, AI, PDF) |
| `ar` | Arabic | Full (CLI, UI, AI, PDF) |
| `ru` | Russian | Full (CLI, UI, AI, PDF) |

## Setting the Language

### CLI

```bash
osint-d2 hunt -u johndoe --lang es
```

### Environment Variable

```env
OSINT_D2_DEFAULT_LANGUAGE=en
```

### Web Dashboard

Use the sidebar dropdown or the `?lang=XX` URL parameter:

```
http://localhost:8000/?lang=ar
```

## How i18n Works

### UI Translations

Dashboard translations are stored as JSON files in `src/adapters/templates/i18n/`:

```
src/adapters/templates/i18n/
├── en.json    # English (reference)
├── es.json    # Spanish
├── pt.json    # Portuguese
├── ar.json    # Arabic
└── ru.json    # Russian
```

The web server loads the appropriate JSON based on the `?lang=` parameter and injects it into the Jinja2 template. JavaScript runtime strings are also translated via a `T` object injected into the page.

### AI Prompts

AI analysis prompts are dynamically constructed in the selected language. The LLM receives instructions in the target language and generates the cognitive profile accordingly.

### PDF Reports

PDF dossiers inherit the language from the investigation. The report template, section headers, and labels are rendered in the selected language.

## Contributing Translations

To add a new language:

1. Copy `src/adapters/templates/i18n/en.json` to `<code>.json`
2. Translate all values — **keys must remain identical**
3. Add the language to the `Language` enum in `src/core/domain/language.py`
4. Add the option to the dashboard language `<select>` in `dashboard.html`
5. Run the i18n consistency test:

```bash
python3 -c "
import json, glob
files = glob.glob('src/adapters/templates/i18n/*.json')
counts = {f.split('/')[-1]: len(json.load(open(f))) for f in files}
print(counts)
assert len(set(counts.values())) == 1, 'Key count mismatch!'
print('All languages consistent ✓')
"
```
