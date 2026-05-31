#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor Boletin Oficial + Noticias + INDEC
Updater diario - corre en GitHub Actions, sin gastar creditos de Claude.

Flujo:
  1. Baja avisos de la primera seccion del Boletin Oficial Nacional (decretos + resoluciones).
  2. Toma indicadores INDEC (configurables abajo).
  3. Resume decretos y agrupa resoluciones usando la API GRATIS de Groq.
  4. Renderiza index.html listo para deployar a Netlify.

Variables de entorno:
  GROQ_API_KEY  -> key gratis de https://console.groq.com/keys

Uso local:
  GROQ_API_KEY=xxx python update.py
"""

import os
import sys
import json
import datetime as dt
import urllib.request
import urllib.error

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"          # modelo gratis de Groq
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

USUARIO = "Valentin Olavarria"
PARTIDO = "Tres de Febrero"

# Endpoint del sumario de la primera seccion del Boletin Oficial.
# Si en los logs de Actions ves que no trae datos, este es el punto a ajustar.
BORA_BASE = "https://www.boletinoficial.gob.ar"
BORA_SUMARIO = BORA_BASE + "/edicion/sumario/primera"

# Indicadores INDEC (se editan a mano cuando salen nuevos; sin scraping fragil).
INDEC_INDICADORES = [
    {"valor": "2,6%", "label": "IPC - Precios al consumidor", "periodo": "Abril 2026"},
    {"valor": "7,5%", "label": "Tasa de desocupacion", "periodo": "4 trim. 2025"},
    {"valor": "3,5%", "label": "EMAE - Actividad economica", "periodo": "Marzo 2026"},
    {"valor": "3,2%", "label": "Produccion industrial", "periodo": "Marzo 2026"},
    {"valor": "46,4M", "label": "Poblacion estimada", "periodo": "Julio 2025"},
]
INDEC_PUBLICACIONES = [
    {"titulo": "Dotacion APN, empresas y sociedades", "fecha": "Abril 2026"},
    {"titulo": "Industria de maquinaria agricola - 1 trim. 2026", "fecha": "Mayo 2026"},
    {"titulo": "Turismo internacional", "fecha": "Mayo 2026"},
]

TIMEOUT = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MonitorBoletin/1.0)",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}


def log(*a):
    print("[monitor]", *a, file=sys.stderr, flush=True)


def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


# --------------------------------------------------------------------------
# 1. BOLETIN OFICIAL NACIONAL
# --------------------------------------------------------------------------
def fetch_boletin():
    out = {"ok": False, "raw": ""}
    try:
        html = http_get(BORA_SUMARIO)
        out["raw"] = html
        out["ok"] = True
        log("Boletin: descarga OK, %d bytes" % len(html))
    except Exception as e:
        log("Boletin ERROR:", repr(e))
    return out


# --------------------------------------------------------------------------
# 2. INDEC
# --------------------------------------------------------------------------
def fetch_indec():
    return {"indicadores": INDEC_INDICADORES, "publicaciones": INDEC_PUBLICACIONES}


# --------------------------------------------------------------------------
# 3. RESUMENES CON GROQ (IA GRATIS)
# --------------------------------------------------------------------------
def groq_chat(prompt, system="Sos un asistente que resume normativa argentina en espanol, claro y breve."):
    if not GROQ_API_KEY:
        log("SIN GROQ_API_KEY: salteo resumenes IA")
        return None
    body = json.dumps({
        "model": GROQ_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={"Authorization": "Bearer " + GROQ_API_KEY,
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        log("Groq HTTPError", e.code, e.read()[:300])
    except Exception as e:
        log("Groq ERROR:", repr(e))
    return None


def resumir(boletin):
    if not boletin.get("raw"):
        return {"decretos": [], "resoluciones_resumen": []}
    prompt = (
        "Te paso el HTML del sumario de la primera seccion del Boletin Oficial argentino. "
        "Devolveme SOLO un JSON con esta forma exacta:\n"
        '{"decretos":[{"numero":"399/2026","tema":"SEGURIDAD SOCIAL","resumen":"...","url":"..."}],'
        '"resoluciones_resumen":[{"organismo":"ANSES","cantidad":2,"resumen":"...","url":"..."}]}\n'
        "Para resoluciones agrupa por organismo con un resumen corto de cada grupo. "
        "Resumenes de maximo 20 palabras. No agregues texto fuera del JSON.\n\nHTML:\n"
        + boletin["raw"][:60000]
    )
    txt = groq_chat(prompt)
    if not txt:
        return {"decretos": [], "resoluciones_resumen": []}
    txt = txt.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
    try:
        return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    except Exception as e:
        log("No pude parsear JSON de Groq:", repr(e))
        return {"decretos": [], "resoluciones_resumen": []}


# --------------------------------------------------------------------------
# 4. RENDER HTML
# --------------------------------------------------------------------------
def render(fecha, resumen, indec):
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    hoy = "%s, %d de %s de %d" % (dias[fecha.weekday()], fecha.day, meses[fecha.month - 1], fecha.year)
    fstamp = fecha.strftime("%d/%m/%Y")

    decretos_html = ""
    for d in resumen.get("decretos", []):
        decretos_html += """
        <article class="card">
          <div class="tag">Decreto</div>
          <div class="meta">{f} - {t}</div>
          <h3>Decreto {n}</h3>
          <p>{r}</p>
          <a href="{u}" target="_blank">Ver texto oficial</a>
        </article>""".format(f=fstamp, t=d.get("tema", ""), n=d.get("numero", ""),
                              r=d.get("resumen", ""), u=d.get("url", BORA_BASE))
    if not decretos_html:
        decretos_html = '<p class="empty">Sin items hoy</p>'

    res_rows = ""
    total_res = 0
    for r in resumen.get("resoluciones_resumen", []):
        try:
            total_res += int(r.get("cantidad", 0) or 0)
        except (ValueError, TypeError):
            pass
        res_rows += """
        <tr><td><strong>{o}</strong> - {c} res. - {r}</td>
        <td><a href="{u}" target="_blank">ver</a></td></tr>""".format(
            o=r.get("organismo", ""), c=r.get("cantidad", ""),
            r=r.get("resumen", ""), u=r.get("url", BORA_BASE))
    if not res_rows:
        res_rows = '<tr><td class="empty">Sin items hoy</td><td></td></tr>'

    indic_html = ""
    for i in indec["indicadores"]:
        indic_html += '<div class="kpi"><div class="kv">{v}</div><div class="kl">{l}</div><div class="kp">{p}</div></div>'.format(
            v=i["valor"], l=i["label"], p=i["periodo"])

    pubs_html = ""
    for p in indec["publicaciones"]:
        pubs_html += '<div class="pub"><h4>{t}</h4><div class="meta">{f} - <a href="https://www.indec.gob.ar" target="_blank">INDEC</a></div></div>'.format(
            t=p["titulo"], f=p["fecha"])

    return TEMPLATE.format(
        titulo="Monitor - " + fstamp, usuario=USUARIO, hoy=hoy, fstamp=fstamp,
        decretos=decretos_html, resoluciones=res_rows, total_res=total_res,
        indicadores=indic_html, publicaciones=pubs_html, partido=PARTIDO)


TEMPLATE = """<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Source+Serif+4:opsz,wght@8..60,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{color-scheme:light}}*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Source Serif 4',Georgia,serif;background:#faf9f7;color:#1a1a1a;line-height:1.6}}
.mh{{background:#1a1a1a;color:#fff;padding:20px 28px}}
.mh h1{{font-family:'Playfair Display',serif;font-size:28px;font-weight:900}}
.mh .dt{{font-family:'JetBrains Mono',monospace;font-size:11px;color:#888;margin-top:4px}}
.ub{{display:inline-block;margin-top:6px;font-family:'JetBrains Mono',monospace;font-size:10px;color:#22c55e;background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);border-radius:20px;padding:2px 10px}}
.wrap{{max-width:880px;margin:0 auto;padding:24px 20px 60px}}
section{{margin-top:34px}}
h2{{font-family:'Playfair Display',serif;font-size:20px;border-bottom:2px solid #1a1a1a;padding-bottom:6px;margin-bottom:16px}}
.card{{background:#fff;border:1px solid #e5e2dc;border-radius:8px;padding:16px;margin-bottom:12px}}
.card h3{{font-family:'Playfair Display',serif;font-size:17px;margin:6px 0}}
.tag{{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:10px;background:#1a1a1a;color:#fff;padding:2px 8px;border-radius:4px}}
.meta{{font-family:'JetBrains Mono',monospace;font-size:11px;color:#888;margin:4px 0}}
.card a,.pub a,.big{{font-family:'JetBrains Mono',monospace;font-size:12px;color:#1d4ed8;text-decoration:none}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e2dc;border-radius:8px;overflow:hidden}}
td{{padding:10px 12px;border-bottom:1px solid #f0eee9;font-size:14px;vertical-align:top}}
.kpis{{display:flex;flex-wrap:wrap;gap:12px}}
.kpi{{flex:1 1 140px;background:#fff;border:1px solid #e5e2dc;border-radius:8px;padding:14px;text-align:center}}
.kv{{font-family:'Playfair Display',serif;font-size:26px;font-weight:900}}
.kl{{font-size:12px;color:#444}}.kp{{font-family:'JetBrains Mono',monospace;font-size:10px;color:#888;margin-top:4px}}
.pub{{background:#fff;border:1px solid #e5e2dc;border-radius:8px;padding:12px;margin-bottom:8px}}
.pub h4{{font-size:14px;font-weight:600}}
.empty{{color:#999;font-style:italic;font-size:14px;padding:6px 0}}
.foot{{margin-top:50px;text-align:center;font-family:'JetBrains Mono',monospace;font-size:11px;color:#999}}
a.big{{display:inline-block;margin-top:10px}}
</style></head>
<body>
<div class="mh">
  <h1>Boletin + Noticias</h1>
  <div class="dt">{hoy}</div>
  <span class="ub">actualizado {fstamp}</span>
</div>
<div class="wrap">
  <section>
    <h2>Decretos del dia</h2>
    {decretos}
  </section>
  <section>
    <h2>Resoluciones - resumen por organismo ({total_res} en total)</h2>
    <table><tbody>{resoluciones}</tbody></table>
    <a class="big" href="https://www.boletinoficial.gob.ar/seccion/primera" target="_blank">Boletin oficial completo</a>
  </section>
  <section>
    <h2>INDEC - Indicadores</h2>
    <div class="kpis">{indicadores}</div>
    <h2 style="margin-top:24px">Ultimas publicaciones</h2>
    {publicaciones}
    <a class="big" href="https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-5-31" target="_blank">Calendario INDEC completo</a>
  </section>
  <div class="foot">Monitor Personal - {usuario} - Actualizacion automatica lunes a viernes 8:00<br>
  Partido de {partido}</div>
</div>
</body></html>"""


def main():
    hoy = dt.date.today()
    log("Corriendo", hoy.isoformat())
    boletin = fetch_boletin()
    resumen = resumir(boletin)
    indec = fetch_indec()
    html = render(hoy, resumen, indec)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    log("index.html escrito:", len(html), "bytes")


if __name__ == "__main__":
    main()
