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
  /* ══════════════════════════════════════════════════════════════════════
     SISTEMA DE DISEÑO OSINT-D2 — alineado con la identidad del informe PDF
     Fuente de verdad de marca: paleta forense esmeralda/teal.

     Escala de elevación (evita el "todo al mismo nivel" que se ve amateur):
       L0 surface-deep   fondo de app
       L1 surface-base   paneles
       L2 surface-card   tarjetas
       L3 surface-raised elementos interactivos / hover
     ══════════════════════════════════════════════════════════════════════ */
  :root {{
    /* — Marca (compartida con el PDF) — */
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

    /* — Superficies: MISMA temperatura de color (verde), solo cambia la luz — */
    --surface-deep:   #04120e;
    --surface-base:   #071b16;
    --surface-card:   #0a231d;
    --surface-raised: #0e2c24;
    --surface-inset:  #030d0a;

    /* — Bordes: capas por opacidad, nunca grises azulados — */
    --border-subtle:  rgba(52, 211, 153, 0.08);
    --border-default: rgba(52, 211, 153, 0.14);
    --border-strong:  rgba(52, 211, 153, 0.26);
    --border-focus:   {BRAND['accent_soft']};

    /* — Texto: una sola rampa, con contraste verificado — */
    --text-primary:   #e8f5f0;
    --text-secondary: #a8c5bb;
    --text-muted:     #7a9d92;
    --text-accent:    {BRAND['accent_soft']};

    /* — Tipografía — */
    --font-sans: {FONT_SANS};
    --font-mono: {FONT_MONO};

    /* — Espaciado y radios: escala fija, no valores ad-hoc — */
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;
    --radius-pill: 999px;

    /* — Sombras: profundidad real, sutiles — */
    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.35);
    --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.40);
    --shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.50);
    --shadow-glow: 0 0 20px rgba(52, 211, 153, 0.18);

    /* — Movimiento — */
    --ease: cubic-bezier(0.4, 0, 0.2, 1);
    --dur: 180ms;
  }}

  /* ── Tipografía ── */
  html, body, .font-sans {{
    font-family: var(--font-sans) !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
  }}
  .font-mono, code, pre, #terminal-logs, input, select, textarea {{
    font-family: var(--font-mono) !important;
    font-feature-settings: "liga" 0;
  }}
  body {{
    background: var(--surface-deep) !important;
    color: var(--text-primary);
  }}

  /* Rejilla forense: ahora en verde de marca, no en cian */
  body {{
    background-image:
      linear-gradient(rgba(52, 211, 153, 0.022) 1px, transparent 1px),
      linear-gradient(90deg, rgba(52, 211, 153, 0.022) 1px, transparent 1px) !important;
    background-size: 32px 32px !important;
  }}

  /* ── Scrollbars ── */
  ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
  ::-webkit-scrollbar-track {{ background: var(--surface-inset); }}
  ::-webkit-scrollbar-thumb {{
    background: rgba(52, 211, 153, 0.20);
    border-radius: var(--radius-pill);
    border: 2px solid var(--surface-inset);
  }}
  ::-webkit-scrollbar-thumb:hover {{ background: rgba(52, 211, 153, 0.40); }}

  /* ── C ABECERA: degradado de portada del PDF, con línea de acento ── */
  header {{
    background: {COVER_GRADIENT} !important;
    border-bottom: 1px solid var(--border-strong) !important;
    box-shadow: var(--shadow-md);
    position: relative;
  }}
  header::after {{
    content: "";
    position: absolute; left: 0; right: 0; bottom: -1px; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(52,211,153,0.55), transparent);
  }}

  /* ── Panel lateral: L1, con separador de acento ── */
  aside {{
    background: var(--surface-base) !important;
    border-color: var(--border-default) !important;
    box-shadow: var(--shadow-md);
    z-index: 5;
  }}

  main {{ background: var(--surface-deep) !important; }}

  /* ── Formularios: foco e hover reales (esto es lo que se siente "barato"
        cuando falta: los inputs no reaccionan) ── */
  input, select, textarea {{
    background: var(--surface-inset) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-size: 12.5px !important;
    transition: border-color var(--dur) var(--ease),
                box-shadow var(--dur) var(--ease),
                background var(--dur) var(--ease) !important;
  }}
  input:hover, select:hover, textarea:hover {{
    border-color: var(--border-strong) !important;
    background: var(--surface-base) !important;
  }}
  input:focus, select:focus, textarea:focus {{
    border-color: var(--border-focus) !important;
    box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.14), var(--shadow-glow) !important;
    background: var(--surface-base) !important;
    outline: none !important;
  }}
  input::placeholder {{ color: var(--text-muted) !important; }}

  /* Select: flecha nativa estilizada */
  select {{
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2334d399' d='M6 9L1 4h10z'/%3E%3C/svg%3E") !important;
    background-repeat: no-repeat !important;
    background-position: right 10px center !important;
    padding-right: 30px !important;
  }}

  /* Etiquetas de formulario: color y peso consistentes */
  label {{
    color: var(--text-secondary) !important;
    letter-spacing: 0.02em;
  }}

  /* ── Botón primario: degradado de marca + glow al hover ── */
  #btn-start {{
    background: linear-gradient(135deg, var(--brand-accent) 0%, var(--brand-accent-deep) 100%) !important;
    color: #f0fdf4 !important;
    border: 1px solid rgba(52, 211, 153, 0.45) !important;
    box-shadow: var(--shadow-md), 0 0 0 0 rgba(52, 211, 153, 0) !important;
    letter-spacing: 0.10em !important;
    transition: transform var(--dur) var(--ease),
                box-shadow var(--dur) var(--ease),
                filter var(--dur) var(--ease) !important;
  }}
  #btn-start:hover {{
    transform: translateY(-1px);
    box-shadow: var(--shadow-lg), 0 0 24px rgba(52, 211, 153, 0.35) !important;
    filter: brightness(1.08);
  }}
  #btn-start:active {{ transform: translateY(0); }}

  /* Botones secundarios (descargas, cancelar): coherentes entre sí */
  #btn-download-pdf, #btn-download-canvas, #btn-cancel {{
    border-radius: var(--radius-md) !important;
    letter-spacing: 0.04em !important;
    transition: all var(--dur) var(--ease) !important;
  }}
  #btn-download-pdf {{
    background: rgba(52, 211, 153, 0.10) !important;
    border: 1px solid var(--border-strong) !important;
    color: var(--text-accent) !important;
  }}
  #btn-download-pdf:hover {{
    background: rgba(52, 211, 153, 0.18) !important;
    box-shadow: var(--shadow-glow);
  }}

  /* ── Tarjetas y contenedores: elevación L2 con borde sutil ── */
  .cyber-card, #report-drawer {{
    background: var(--surface-card) !important;
    border-color: var(--border-default) !important;
  }}
  #report-drawer {{
    box-shadow: 0 -12px 40px rgba(0, 0, 0, 0.55) !important;
    border-top: 1px solid var(--border-strong) !important;
  }}

  /* ── Consola / terminal: superficie hundida, la más oscura ── */
  #terminal-logs {{
    background: var(--surface-inset) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-secondary) !important;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.40);
  }}

  /* ── Acentos de marca (reemplazan la paleta cian) ── */
  .text-cyber-accent {{ color: var(--text-accent) !important; }}
  .bg-cyber-accent {{ background: var(--brand-accent) !important; }}
  .border-cyber-accent {{ border-color: var(--brand-accent) !important; }}
  .border-cyber-border {{ border-color: var(--border-default) !important; }}
  .cyber-orange, .text-cyber-orange {{ color: var(--brand-orange) !important; }}

  /* ── Título de sección: réplica de .section-title del PDF ── */
  .section-title-brand {{
    border-left: 4px solid var(--brand-accent);
    background: linear-gradient(90deg, var(--brand-accent-glow), transparent 65%);
    text-transform: uppercase;
    letter-spacing: 0.10em;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    padding: 8px 14px;
    color: var(--text-primary);
    font-weight: 700;
  }}

  /* Encabezados de sección del panel: barra de acento consistente */
  aside .text-cyber-accent.uppercase,
  #report-drawer .text-cyber-accent.uppercase {{
    letter-spacing: 0.10em !important;
  }}

  /* ── Badges: píldoras consistentes con el PDF ── */
  .net-badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: var(--radius-pill);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    background: rgba(52, 211, 153, 0.13);
    color: var(--text-accent);
    border: 1px solid var(--border-strong);
  }}

  /* ── Barras de confianza: idénticas a .confidence-bar del PDF ── */
  .confidence-high {{ background: linear-gradient(90deg, #10b981, #059669) !important; }}
  .confidence-mid  {{ background: linear-gradient(90deg, #f59e0b, #d97706) !important; }}
  .confidence-low  {{ background: linear-gradient(90deg, #ef4444, #dc2626) !important; }}

  /* ── Banda de portada (cover-band del PDF) ── */
  .cover-band {{
    display: inline-block;
    border: 1px solid rgba(52, 211, 153, 0.6);
    color: var(--text-accent);
    padding: 6px 20px;
    letter-spacing: 0.30em;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    background: rgba(15, 118, 110, 0.20);
    border-radius: var(--radius-sm);
  }}

  /* ── Micro-interacciones: lo que hace que se sienta cuidado ── */
  button {{
    transition: transform var(--dur) var(--ease),
                box-shadow var(--dur) var(--ease),
                background var(--dur) var(--ease),
                color var(--dur) var(--ease) !important;
  }}
  button:active {{ transform: scale(0.985); }}
  button:focus-visible {{
    outline: none;
    box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.30) !important;
  }}

  /* Feedback de foco en cualquier control de formulario */
  *:focus-visible {{
    outline: 2px solid var(--border-focus);
    outline-offset: 2px;
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
