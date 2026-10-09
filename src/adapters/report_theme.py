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

  /* ── Panel lateral: L1, con separador de acento ──
        Layout interno: el formulario hace scroll dentro de su propio espacio y
        la consola conserva una altura util. Sin esto, en desktop el formulario
        empuja la consola fuera y el panel se corta. */
  aside {{
    background: var(--surface-base) !important;
    border-color: var(--border-default) !important;
    box-shadow: var(--shadow-md);
    z-index: 5;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    /* Sin esto el aside se encoge a la altura de su contenido (~472px) y el
       formulario queda amputado a la mitad en pantallas altas.
       !important porque las utilidades de Tailwind tienen la misma
       especificidad y se inyectan despues. */
    align-self: stretch !important;
    height: 100% !important;
    min-height: 0 !important;
    max-height: 100% !important;
  }}
  /* El contenedor de la fila tambien debe permitir el estirado completo */
  body > div.flex-1 {{
    min-height: 0;
    align-items: stretch;
  }}
  /* ── Reparto del panel lateral ──
     El panel alberga el formulario, que es su proposito. La consola del agente
     vive en el area principal (pestana), no compite por el espacio.
     El formulario recibe todo el alto disponible y hace scroll si hace falta:
     es preferible a un panel amputado a 200px. */
  aside {{
    justify-content: flex-start;
  }}
  #vector-form {{
    flex: 1 1 auto;
    overflow-y: auto;
    min-height: 0;
    scrollbar-gutter: stable;
    /* El padding inferior evita que el ultimo control quede pegado al borde */
    padding-bottom: 18px !important;
  }}
  /* La cabecera plegable no debe consumir mas de lo necesario */
  aside > div:first-child {{
    flex: 0 0 auto;
  }}

  main {{ background: var(--surface-deep) !important; }}

  /* ── Escala tipográfica: 5 pasos, nada fuera de esto ──
        El "text-xs" de Tailwind (12px) se usa por todas partes mezclado con
        11px y 10px; eso destruye la jerarquía. Definimos una escala. */
  :root {{
    --fs-micro:  10px;   /* metadatos, contadores */
    --fs-xs:     11.5px; /* etiquetas de formulario */
    --fs-sm:     13px;   /* cuerpo de UI, inputs */
    --fs-base:   15px;   /* texto de lectura */
    --fs-lg:     18px;   /* títulos de sección */
    --fs-xl:     24px;   /* cifras destacadas */
  }}

  /* ── Controles de formulario: PADDING REAL, no solo min-height ──
        (min-height sin padding vertical es un parche: el texto queda pegado
        al borde superior en algunos motores y el objetivo se ve tosco) */
  input, select, textarea {{
    background: var(--surface-inset) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-size: var(--fs-sm) !important;
    line-height: 1.4 !important;
    padding: 10px 12px !important;
    height: auto !important;
    min-height: 40px !important;
    transition: border-color var(--dur) var(--ease),
                box-shadow var(--dur) var(--ease),
                background var(--dur) var(--ease) !important;
  }}
  input:hover, select:hover, textarea:hover {{
    border-color: var(--border-strong) !important;
    background: var(--surface-base) !important;
  }}
  /* En pantallas tactiles el minimo sube a 44px (Apple HIG) */
  @media (max-width: 1024px) {{
    input, select, textarea {{ min-height: 44px !important; }}
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
    padding: 11px 34px 11px 13px !important;
  }}

  /* ── Grupos de formulario: agrupan por PROPOSITO, no por tipo de campo
        (Ley de Proximidad + Region Comun: lo agrupado se lee como un todo) ── */
  .form-group {{
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    background: rgba(7, 27, 22, 0.42);
    padding: 11px 12px;
    display: flex;
    flex-direction: column;
    gap: 9px;
    transition: border-color var(--dur) var(--ease);
  }}
  .form-group:hover {{ border-color: var(--border-default); }}

  .form-group--collapsed {{
    padding: 0;
    gap: 0;
    background: transparent;
    border-color: transparent;
  }}

  .form-group-label {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--fs-xs);
    font-weight: 700;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    color: var(--text-accent);
    padding-bottom: 2px;
  }}
  .form-group-label--warn {{ color: var(--brand-orange); }}
  .form-group-label i:first-child {{ opacity: 0.85; font-size: 11px; }}

  .form-group-label--btn {{
    width: 100%;
    justify-content: space-between;
    min-height: 44px;
    padding: 0 14px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: rgba(7, 27, 22, 0.42);
    cursor: pointer;
    transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease);
  }}
  .form-group-label--btn:hover {{
    background: var(--surface-raised);
    border-color: var(--border-strong);
  }}
  .form-group-label--btn > span {{ display: flex; align-items: center; gap: 8px; }}

  .badge-optional {{
    margin-left: auto;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.06em;
    padding: 2px 8px;
    border-radius: var(--radius-pill);
    background: rgba(245, 158, 11, 0.14);
    color: var(--brand-orange);
    border: 1px solid rgba(245, 158, 11, 0.28);
    text-transform: uppercase;
  }}

  .field {{ display: flex; flex-direction: column; gap: 4px; }}
  .field-hint {{
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.45;
    margin: 0;
  }}
  .field-icon {{ margin-right: 4px; opacity: 0.7; font-size: 10px; }}
  .req {{ color: var(--brand-orange); font-weight: 700; }}

  /* Etiquetas de formulario: escala y peso del sistema */
  label {{
    color: var(--text-secondary) !important;
    font-size: var(--fs-xs) !important;
    font-weight: 600 !important;
    letter-spacing: 0.03em;
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

  /* ── CONSOLA: jerarquia visual en el flujo de log ──
        Un muro de texto mono de un solo color no se lee. Los niveles de log
        deben distinguirse por color Y por forma (no solo color: WCAG 1.4.1). */
  #terminal-logs > div {{ padding-left: 2px; }}

  /* ── DOSSIER: la pieza que el usuario se lleva. Debe verse como el PDF ──
        Cifras destacadas con la tipografia y el color del informe. */
  #report-confidence {{
    font-size: var(--fs-xs) !important;
    font-weight: 700 !important;
    letter-spacing: 0.06em !important;
    padding: 3px 10px !important;
    border-radius: var(--radius-pill) !important;
    background: rgba(52, 211, 153, 0.13) !important;
    color: var(--text-accent) !important;
    border: 1px solid var(--border-strong) !important;
  }}

  /* Tarjetas de hallazgo: el patron .highlights-list del PDF */
  #report-highlights > * {{
    padding: 9px 13px;
    margin-bottom: 6px;
    background: rgba(7, 27, 22, 0.60);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--brand-accent);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--text-secondary);
    transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease);
  }}
  #report-highlights > *:hover {{
    background: rgba(14, 44, 36, 0.75);
    border-left-color: var(--brand-accent-soft);
  }}

  /* Resumen del informe: legible, no un bloque de mono crudo */
  #report-summary {{
    background: rgba(3, 13, 10, 0.65) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: 14px !important;
    font-size: 12.5px !important;
    line-height: 1.65 !important;
    color: var(--text-secondary) !important;
  }}

  /* ├ Encabezado del dossier: separador de acento como en el PDF */
  #report-drawer > div:first-child {{
    border-bottom: 1px solid var(--border-default) !important;
    padding-bottom: 12px !important;
    margin-bottom: 14px !important;
  }}

  /* ── Contador de nodos: chip flotante con el tratamiento de marca ── */
  #graph-container > div:first-child {{
    background: rgba(4, 18, 14, 0.82) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: var(--radius-pill) !important;
    padding: 6px 14px !important;
    box-shadow: var(--shadow-md);
    color: var(--text-muted) !important;
    letter-spacing: 0.06em;
  }}

  /* ── Estados vacios: el detalle que separa un producto de un prototipo ── */
  .empty-state {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 32px 20px;
    text-align: center;
    color: var(--text-muted);
  }}
  .empty-state i {{ font-size: 26px; opacity: 0.35; }}
  .empty-state p {{ margin: 0; font-size: 12.5px; line-height: 1.5; max-width: 340px; }}

  /* ── Pestanas de vista: control segmentado, no enlaces sueltos ──
        Un solo control agrupado (Ley de Region Comun) con indicador de
        seleccion claro (Nielsen #1: visibilidad del estado). */
  .view-tabs {{
    display: flex;
    gap: 4px;
    padding: 8px 10px 0;
    border-bottom: 1px solid var(--border-default);
    background: var(--surface-base);
    flex-shrink: 0;
  }}

  .view-tab {{
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 9px 16px;
    min-height: 40px;
    border: none;
    border-bottom: 2px solid transparent;
    background: transparent;
    color: var(--text-muted);
    font-size: var(--fs-xs);
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    cursor: pointer;
    border-radius: var(--radius-sm) var(--radius-sm) 0 0;
    transition: color var(--dur) var(--ease),
                background var(--dur) var(--ease),
                border-color var(--dur) var(--ease);
  }}
  .view-tab:hover {{
    color: var(--text-secondary);
    background: rgba(52, 211, 153, 0.06);
  }}
  .view-tab.is-active {{
    color: var(--text-accent);
    border-bottom-color: var(--brand-accent);
    background: rgba(52, 211, 153, 0.08);
  }}
  .view-tab i {{ font-size: 11px; opacity: 0.9; }}

  /* Panel de vista activo */
  .view-panel {{ min-height: 0; }}

  /* ── En desktop los grupos no necesitan marco: la etiqueta actua de
        separador y se gana ~60px de alto sin perder la agrupacion visual. ── */
  @media (min-width: 1024px) {{
    .form-group {{
      border: none;
      background: transparent;
      padding: 0;
      gap: 8px;
    }}
    .form-group + .form-group {{
      border-top: 1px solid var(--border-subtle);
      padding-top: 10px;
    }}
    .form-group-label {{
      font-size: 10.5px;
      opacity: 0.95;
    }}
    .form-group-label--btn {{
      border: 1px solid var(--border-default);
      background: rgba(7, 27, 22, 0.42);
      padding: 0 12px;
      min-height: 40px;
    }}
  }}

  /* ── Cadena de altura del layout ──
     Sin esto el div.flex-1 se queda en 472px (altura de su contenido) y el
     panel lateral aparece amputado a la mitad en pantallas altas.
     html y body deben tener altura resuelta para que flex:1 funcione. */
  html, body {{ height: 100%; overflow: hidden; }}

  /* ── Cadena de altura: el bug que dejaba el panel a 472px ──
     `flex: 1 1 0%` (la utilidad .flex-1 de Tailwind) colapsa a la altura del
     contenido cuando el contenedor flex no tiene una altura resuelta por
     height. Con `1 1 auto` + height:0 el hijo se estira de verdad.
     Ademas el <main> que queda como hijo suelto del body debe ocultarse:
     rompe el reparto al ser un segundo hijo directo. */
  body > div.flex-1 {{
    flex: 1 1 auto !important;
    height: 0 !important;
    min-height: 0 !important;
  }}
  body > main {{ display: none !important; }}
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
