"""Tokens de diseño compartidos entre el PDF y el dashboard web.

La identidad visual nace en el informe PDF (esmeralda/teal forense) y se replica
aquí para que la web hable el mismo idioma visual. Un solo origen de verdad:
si cambia un color, cambia en el PDF y en la web a la vez.

Uso:
    from adapters.report_theme import BRAND, PDF_THEME_CSS
    # en web_server.py, inyectar PDF_THEME_CSS en el <head> del dashboard
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Paleta de marca (extraída del PDF: reports/*.html -> :root)
# ---------------------------------------------------------------------------
BRAND = {
    # Verdes forenses (identidad principal del PDF)
    "dark": "#0a1f1a",          # superficie más oscura / cabeceras de tabla
    "ink": "#1a2e28",           # texto principal sobre claro
    "muted": "#5a7d6e",         # texto secundario
    "accent": "#0d9488",        # acento principal (6.76:1 sobre dark)
    "accent_deep": "#0f766e",   # acento profundo (enlaces, énfasis)
    "accent_soft": "#34d399",   # acento brillante (8.93:1 sobre dark)
    "accent_glow": "rgba(52, 211, 153, 0.15)",
    # Semánticos
    "red": "#ef4444",
    "orange": "#f59e0b",
    "green": "#10b981",
    # Superficies (tema claro del PDF)
    "surface": "#ffffff",
    "surface_alt": "#f7faf9",
    "border": "rgba(31, 41, 51, 0.10)",
    "shadow": "rgba(15, 23, 42, 0.06)",
}

# Degradado de la portada del PDF, replicado en la cabecera de la web.
COVER_GRADIENT = (
    "linear-gradient(155deg, #041914 0%, #0a2820 40%, #0d3429 70%, #0f3d30 100%)"
)

# Tipografía del PDF.
FONT_SANS = '"IBM Plex Sans", "Inter", "Segoe UI", Roboto, sans-serif'
FONT_MONO = '"JetBrains Mono", "SF Mono", Menlo, monospace'


# ---------------------------------------------------------------------------
# CSS de la identidad de marca para el dashboard web.
#
# El dashboard es dark-first (identidad forense); la paleta del PDF es clara
# para impresión. Esta hoja alinea la web con el PDF sin romper el tema oscuro:
# usa los verdes de marca como acentos y el degradado de portada en la cabecera.
#
# Contraste verificado sobre --brand-dark (#0a1f1a):
#   accent #0d9488 = 6.76:1 · accent-soft #34d399 = 8.93:1  -> WCAG AA/AAA
# ---------------------------------------------------------------------------
PDF_THEME_CSS = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style id="osint-d2-brand-theme">
  :root {{
    /* Paleta de marca compartida con el PDF */
    --brand-dark: {BRAND['dark']};
    --brand-ink: {BRAND['ink']};
    --brand-muted: {BRAND['muted']};
    --brand-accent: {BRAND['accent']};
    --brand-accent-deep: {BRAND['accent_deep']};
    --brand-accent-soft: {BRAND['accent_soft']};
    --brand-accent-glow: {BRAND['accent_glow']};
    --brand-red: {BRAND['red']};
    --brand-orange: {BRAND['orange']};
    --brand-green: {BRAND['green']};

    /* Superficies oscuras del dashboard, derivadas del verde de marca */
    --surface-deep: #041914;
    --surface-base: #061c17;
    --surface-card: #0a221c;
    --surface-raised: #0d2b23;

    --font-sans: {FONT_SANS};
    --font-mono: {FONT_MONO};
  }}

  body {{
    font-family: var(--font-sans) !important;
    background: var(--surface-deep);
  }}

  /* Tailwind fija su propia pila en .font-sans; alinearla con la del PDF */
  .font-sans, html {{
    font-family: var(--font-sans) !important;
  }}

  /* Cabecera con el degradado de la portada del PDF */
  header {{
    background: {COVER_GRADIENT} !important;
    border-bottom: 1px solid rgba(52, 211, 153, 0.22) !important;
  }}

  /* Panel lateral: superficie de marca en vez del gris azulado */
  aside {{
    background: linear-gradient(180deg, #08201a 0%, #061a15 100%) !important;
    border-color: rgba(52, 211, 153, 0.14) !important;
  }}

  /* El área del grafo mantiene el fondo profundo */
  main {{ background: var(--surface-deep) !important; }}

  /* Tarjetas y bloques: mismo lenguaje que .card del PDF */
  .cyber-card {{
    background: var(--surface-card) !important;
    border-color: rgba(52, 211, 153, 0.14) !important;
  }}

  /* Acento principal: teal de marca en lugar del cian del dashboard */
  .text-cyber-accent {{ color: var(--brand-accent-soft) !important; }}
  .bg-cyber-accent {{ background: var(--brand-accent) !important; }}
  .border-cyber-accent {{ border-color: var(--brand-accent) !important; }}
  .border-cyber-border {{ border-color: rgba(52, 211, 153, 0.14) !important; }}

  /* Los títulos de sección replican .section-title del PDF:
     barra izquierda de acento + degradado hacia transparente */
  .section-title-brand {{
    border-left: 5px solid var(--brand-accent);
    background: linear-gradient(90deg, var(--brand-accent-glow), transparent 60%);
    text-transform: uppercase;
    letter-spacing: 1px;
    border-radius: 0 4px 4px 0;
    padding: 8px 16px;
  }}

  /* Botón primario: el teal de marca, coherente con la portada del PDF */
  #btn-start {{
    background: linear-gradient(135deg, var(--brand-accent) 0%, var(--brand-accent-deep) 100%) !important;
    color: #f0fdf4 !important;
    box-shadow: 0 2px 12px rgba(13, 148, 136, 0.30);
  }}
  #btn-start:hover {{
    box-shadow: 0 4px 20px rgba(52, 211, 153, 0.45);
    filter: brightness(1.08);
  }}

  /* Barras de confianza, idénticas a .confidence-bar del PDF */
  .confidence-high {{ background: linear-gradient(90deg, #10b981, #059669) !important; }}
  .confidence-mid  {{ background: linear-gradient(90deg, #f59e0b, #d97706) !important; }}
  .confidence-low  {{ background: linear-gradient(90deg, #ef4444, #dc2626) !important; }}

  /* Badges de red: mismo tratamiento que .net-badge del PDF */
  .net-badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    background: rgba(52, 211, 153, 0.15);
    color: var(--brand-accent-soft);
    border: 1px solid rgba(52, 211, 153, 0.25);
  }}

  /* Fuente monoespaciada compartida para datos técnicos */
  .font-mono, code, pre, #terminal-logs {{
    font-family: var(--font-mono) !important;
  }}

  /* Logos y etiquetas tipo "banda" de la portada */
  .cover-band {{
    display: inline-block;
    border: 1px solid rgba(52, 211, 153, 0.6);
    color: var(--brand-accent-soft);
    padding: 6px 20px;
    letter-spacing: 4px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    background: rgba(15, 118, 110, 0.20);
    border-radius: 4px;
  }}
</style>
"""


def inject_brand_theme(html: str) -> str:
    """Inyecta la hoja de identidad de marca en el <head> del dashboard.

    Idempotente: si el tema ya está presente, no lo duplica.
    """
    if 'id="osint-d2-brand-theme"' in html:
        return html
    marker = "</head>"
    if marker in html:
        return html.replace(marker, f"{PDF_THEME_CSS}\n{marker}", 1)
    return PDF_THEME_CSS + html
