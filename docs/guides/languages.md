# Language Support

OSINT-D2 supports 5 languages across the CLI options, dashboard, graph, AI prompts, and PDF reports.

## Supported Languages

| Code | Language | Notes |
|------|----------|-------|
| `en` | English | Reference language |
| `es` | Spanish | Neutral Spanish |
| `pt` | Portuguese | |
| `ar` | Arabic | Right-to-left dashboard |
| `ru` | Russian | |

!!! note "Help us improve the translations"
    The Portuguese, Arabic, and Russian strings haven't been reviewed by native speakers. If something reads wrong, please open an issue or a pull request.

The CLI's own messages are in English. `--language` sets the language of the AI analysis and reports.

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

The agent's prompts live in `src/core/services/agent_prompts.py`, with one entry per language. A test checks that every language keeps the same rules and score guidance.

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
4. Add the system prompts in `src/adapters/ai_analyst.py` and `src/core/services/agent_prompts.py`
5. Add the option to both language selectors in `dashboard.html`
6. Add the code to `test_i18n_files_share_the_same_keys`, then run the tests:

```bash
poetry run pytest tests/test_web_server.py
```

The tests check that every language has the same keys and that the dashboard uses only keys that exist. Keep placeholders such as `{target}` unchanged in `log_*` and `graph` strings.

!!! tip
    The Spanish system prompt uses "español neutro" (neutral Spanish) — avoiding regional slang to maximize clarity for all Spanish-speaking users.
