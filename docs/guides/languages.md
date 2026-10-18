# Language Support

OSINT-D2 supports 5 languages across the **entire stack**: CLI interface, web dashboard, AI system prompts, and PDF reports. This is not superficial label translation — the AI agent's reasoning instructions change per language.

## Supported Languages

| Code | Language | CLI | Dashboard | AI Prompts | PDF Reports |
|------|----------|-----|-----------|------------|-------------|
| `en` | English | ✅ | ✅ | ✅ | ✅ |
| `es` | Spanish | ✅ | ✅ | ✅ | ✅ |
| `pt` | Portuguese | ✅ | ✅ | ✅ | ✅ |
| `ar` | Arabic | ✅ | ✅ | ✅ | ✅ |
| `ru` | Russian | ✅ | ✅ | ✅ | ✅ |

---

## Setting the Language

=== "CLI"

    ```bash
    osint-d2 hunt -u johndoe --language es
    ```

=== "Environment"

    ```env
    OSINT_D2_DEFAULT_LANGUAGE=en
    ```

=== "Web Dashboard"

    Use the sidebar dropdown or the URL parameter:

    ```
    http://localhost:8000/?lang=ar
    ```

---

## How It Works Under the Hood

### AI System Prompts

The agent's system prompt is **dynamically constructed** based on the investigation language. This isn't just translation — the methodology, rules, and score interpretation guides are all written natively for each language.

=== "English"

    ```
    You are an expert OSINT investigator and Criminal Profiler.
    Your objective is to build a comprehensive profile of the
    target person.

    METHOD:
    1. Start with what you know (provided username/email)
    2. Use the tools to gather evidence from multiple sources
    3. Analyze results and decide what to investigate next
    4. PIVOT: if you find new emails, usernames, aliases...

    RESPONSE LANGUAGE: English.
    ```

=== "Spanish"

    ```
    Eres un investigador OSINT experto y Perfilador Criminalista.
    Tu objetivo es construir un perfil completo de la persona
    indicada.

    MÉTODO:
    1. Empieza con lo que sabes (username/email proporcionado)
    2. Usa las herramientas para recopilar evidencia
    3. Analiza los resultados y decide qué investigar después
    4. PIVOTEA: si encuentras emails, usernames, aliases...

    IDIOMA DE RESPUESTA: Español neutro.
    ```

The prompts also include **language-specific score interpretation** so the LLM doesn't misinterpret BM25 or stylometric scores.

### Dashboard Translations

UI translations are stored as JSON files in `src/adapters/templates/i18n/`:

```
src/adapters/templates/i18n/
├── en.json    # English (reference)
├── es.json    # Spanish
├── pt.json    # Portuguese
├── ar.json    # Arabic
└── ru.json    # Russian
```

The FastAPI server loads the appropriate JSON based on `?lang=` and injects it into the Jinja2 template. JavaScript runtime strings use a `T` object:

```javascript
// In the browser — T is injected by the server
document.getElementById("title").textContent = T.investigation_title;
document.getElementById("start").textContent = T.btn_start;
```

### PDF Reports

PDF dossiers inherit the language from the investigation. Section headers (`IDENTITY & DEMOGRAPHICS`, `PERFIL PSICOLÓGICO`, etc.), labels, and classification tags are all rendered in the selected language.

---

## Contributing Translations

To add a new language:

1. Copy `src/adapters/templates/i18n/en.json` to `<code>.json`
2. Translate all values — **keys must remain identical**
3. Add the language to the `Language` enum in `src/core/domain/language.py`
4. Add the system prompt translation in `src/core/services/agent_engine.py`
5. Add the option to the dashboard `<select>` in `dashboard.html`
6. Run the consistency test:

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

!!! tip
    The Spanish system prompt uses "español neutro" (neutral Spanish) — avoiding regional slang to maximize clarity for all Spanish-speaking users.
