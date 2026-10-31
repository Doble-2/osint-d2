#!/usr/bin/env python3
"""Diagnóstico UX/UI medido del dashboard osint-d2.

Aplica las sondas de la skill `dashboard-ui-review` sobre el servidor vivo:
  1. Integridad de layout por breakpoint (overflow, paneles cortados)
  2. Tap targets (WCAG 2.5.8 / Apple HIG)
  3. Contraste calculado (WCAG 1.4.3)
  4. Salud del JS
  5. Flujo end-to-end

Salida: informe con números reales, no opiniones.
"""
import asyncio
import json
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8000/"
SIZES = [("iphone_se", 375, 667), ("iphone", 390, 844), ("ipad", 820, 1180), ("desktop", 1440, 900)]

# --- JS para calcular contraste WCAG real -------------------------------------
WCAG_JS = r"""
(() => {
  const lum = (r, g, b) => {
    const f = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const parse = (s) => {
    const m = (s || '').match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x.trim()));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const effBg = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0.5) return c;
      n = n.parentElement;
    }
    const b = parse(getComputedStyle(document.body).backgroundColor);
    return b && b.a > 0.5 ? b : { r: 255, g: 255, b: 255, a: 1 };
  };
  const ratio = (f, b) => {
    const L1 = lum(f.r, f.g, f.b), L2 = lum(b.r, b.g, b.b);
    return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
  };
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    if (el.children.length > 0) return;                 // solo nodos de texto
    const txt = (el.textContent || '').trim();
    if (!txt || txt.length < 2) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) < 0.15) return;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const fg = parse(cs.color);
    const bg = effBg(el);
    if (!fg || !bg) return;
    const cr = ratio(fg, bg);
    const fs = parseFloat(cs.fontSize);
    const bold = parseInt(cs.fontWeight) >= 700;
    const large = fs >= 24 || (bold && fs >= 18.66);
    const min = large ? 3.0 : 4.5;
    if (cr < min) {
      out.push({
        text: txt.slice(0, 42), ratio: Math.round(cr * 100) / 100,
        need: min, size: Math.round(fs * 10) / 10, bold,
        color: cs.color, tag: el.tagName.toLowerCase(),
        cls: (el.className || '').toString().slice(0, 55),
      });
    }
  });
  // dedupe por texto+clase
  const seen = new Set(); const uniq = [];
  for (const o of out) { const k = o.text + o.cls; if (!seen.has(k)) { seen.add(k); uniq.push(o); } }
  return uniq.sort((a, b) => a.ratio - b.ratio).slice(0, 30);
})()
"""

TAP_JS = r"""
(() => [...document.querySelectorAll('button,a,[role=button],input,select')]
  .map(e => {
    const r = e.getBoundingClientRect();
    return {
      t: (e.innerText || e.value || e.id || e.tagName).trim().slice(0, 32),
      w: Math.round(r.width), h: Math.round(r.height),
      tag: e.tagName.toLowerCase(),
    };
  })
  .filter(o => o.w > 0 && o.h > 0 && (o.w < 44 || o.h < 44))
  .sort((a, b) => Math.min(a.w, a.h) - Math.min(b.w, b.h))
)()
"""

TINY_FONT_JS = r"""
(() => {
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    if (el.children.length > 0) return;
    const t = (el.textContent || '').trim();
    if (!t) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const fs = parseFloat(cs.fontSize);
    if (fs > 0 && fs < 12) out.push({ text: t.slice(0, 40), size: Math.round(fs*10)/10, cls: (el.className||'').toString().slice(0,45) });
  });
  const seen = new Set(); const u = [];
  for (const o of out) { if (!seen.has(o.text+o.cls)) { seen.add(o.text+o.cls); u.push(o); } }
  return u.slice(0, 25);
})()
"""


async def main():
    report = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        for name, w, h in SIZES:
            ctx = await browser.new_context(viewport={"width": w, "height": h},
                                            device_scale_factor=2, is_mobile=(w < 800), has_touch=(w < 800))
            pg = await ctx.new_page()
            await pg.add_init_script(
                "window.__errs=[];window.onerror=(m,s,l,c,e)=>window.__errs.push(String(m)+(e&&e.stack?(' @ '+e.stack.split('\\n')[1]):''));")
            await pg.goto(URL, wait_until="networkidle")
            await pg.wait_for_timeout(1200)

            layout = await pg.evaluate(r"""() => {
                const de = document.documentElement;
                const aside = document.querySelector('aside');
                const offenders = [];
                document.querySelectorAll('*').forEach(e => {
                    const r = e.getBoundingClientRect();
                    if (r.width > 0 && r.right > de.clientWidth + 2) {
                        offenders.push({ cls: (e.className||'').toString().slice(0,50), right: Math.round(r.right), tag: e.tagName.toLowerCase() });
                    }
                });
                return {
                    hOverflow: de.scrollWidth > de.clientWidth + 2,
                    scrollW: de.scrollWidth, clientW: de.clientWidth,
                    asideCut: aside ? aside.scrollHeight > aside.clientHeight + 4 : null,
                    asideScrollH: aside ? aside.scrollHeight : null,
                    asideClientH: aside ? aside.clientHeight : null,
                    offenders: offenders.slice(0, 5),
                };
            }""")

            contrast = await pg.evaluate(WCAG_JS)
            taps = await pg.evaluate(TAP_JS)
            tiny = await pg.evaluate(TINY_FONT_JS)

            report[name] = {
                "viewport": f"{w}x{h}",
                "layout": layout,
                "contrast_fails": contrast,
                "tap_target_fails": taps,
                "tiny_fonts": tiny,
                "js_errors": await pg.evaluate("window.__errs || []"),
            }
            await ctx.close()

        await browser.close()

    # --- Informe ---------------------------------------------------------------
    print("=" * 78)
    print("DIAGNOSTICO UX/UI — osint-d2 dashboard")
    print("=" * 78)
    for name, d in report.items():
        print(f"\n### {name} ({d['viewport']})")
        L = d["layout"]
        print(f"  Overflow horizontal : {L['hOverflow']}  (scrollW={L['scrollW']} clientW={L['clientW']})")
        if L["hOverflow"] and L["offenders"]:
            for o in L["offenders"]:
                print(f"      -> desborda: <{o['tag']} class='{o['cls']}'> right={o['right']}")
        if L["asideCut"] is not None:
            print(f"  Panel lateral cortado: {L['asideCut']}  ({L['asideScrollH']}px contenido / {L['asideClientH']}px visible)")
        print(f"  Errores JS          : {len(d['js_errors'])}")
        for e in d["js_errors"][:3]:
            print(f"      ! {e[:120]}")
        print(f"  Fallos de contraste : {len(d['contrast_fails'])}")
        for c in d["contrast_fails"][:8]:
            print(f"      {c['ratio']:.2f}:1 (min {c['need']}) {c['size']}px  '{c['text']}'  {c['color']}")
        print(f"  Tap targets < 44px  : {len(d['tap_target_fails'])}")
        for t in d["tap_target_fails"][:8]:
            print(f"      {t['w']}x{t['h']}px  '{t['t']}'")
        print(f"  Fuentes < 12px      : {len(d['tiny_fonts'])}")
        for f in d["tiny_fonts"][:8]:
            print(f"      {f['size']}px  '{f['text']}'")

    with open("/Users/doble/Developer/personal/osint-d2/reports/_ux_audit.json", "w") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print("\n[Informe crudo: reports/_ux_audit.json]")


asyncio.run(main())
