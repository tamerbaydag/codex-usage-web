#!/usr/bin/env python3
import json, os, subprocess, html, time, threading
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ACCESS_TOKEN = os.environ.get('CODEX_USAGE_SECRET', '').strip()
SECRET_PATH = '/' + ACCESS_TOKEN if ACCESS_TOKEN else '/'
TZ = ZoneInfo(os.environ.get('TZ_NAME', 'Europe/Istanbul'))
SESSION_KEY = os.environ.get('OPENCLAW_SESSION_KEY', '').strip()
REFRESH_SECONDS = int(os.environ.get('REFRESH_SECONDS', '30'))

FAVICON_SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="Codex Usage favicon">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#050b12"/>
      <stop offset="100%" stop-color="#0b1624"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#28d6b3"/>
      <stop offset="100%" stop-color="#20bfa0"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="112" fill="url(#bg)"/>
  <rect x="34" y="34" width="444" height="444" rx="96" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="4"/>
  <path d="M126 148h70v216h-70zM216 148h170v56H216zM216 236h132v52H216zM216 324h170v40H216z" fill="#e8eef7" opacity="0.92"/>
  <circle cx="360" cy="184" r="18" fill="url(#accent)"/>
  <circle cx="332" cy="262" r="14" fill="url(#accent)" opacity="0.85"/>
  <circle cx="384" cy="344" r="12" fill="url(#accent)" opacity="0.7"/>
</svg>'''
FAVICON_PATH = Path(__file__).with_name('favicon-c.svg')
if FAVICON_PATH.exists():
    FAVICON_SVG = FAVICON_PATH.read_bytes()

SNAPSHOT = None
SNAPSHOT_ERROR = None
SNAPSHOT_LOCK = threading.Lock()


def fmt_reset(ms):
    if not ms:
        return '-'
    dt = datetime.fromtimestamp(ms / 1000, TZ)
    now = datetime.now(TZ)
    sec = max(0, int((dt - now).total_seconds()))
    h, rem = divmod(sec, 3600)
    m, _ = divmod(rem, 60)
    if h >= 24:
        d, h = divmod(h, 24)
        left = f'{d}g {h}s'
    elif h:
        left = f'{h}s {m}dk'
    else:
        left = f'{m}dk'
    return f'{dt:%Y-%m-%d %H:%M} ({left})'


def build_snapshot():
    raw = subprocess.check_output([os.environ.get('OPENCLAW_BIN', '/home/master/.npm-global/bin/openclaw'), 'status', '--usage', '--json'], text=True, timeout=25)
    data = json.loads(raw)
    provider = next((p for p in data.get('usage', {}).get('providers', []) if p.get('provider') == 'openai-codex'), {})
    sessions = data.get('sessions', {}).get('recent', [])
    sess = next((s for s in sessions if SESSION_KEY and s.get('key') == SESSION_KEY), sessions[0] if sessions else {})
    windows = []
    for w in provider.get('windows', []):
        used = int(w.get('usedPercent') or 0)
        windows.append({
            'label': w.get('label', '-'),
            'used': used,
            'remaining': max(0, 100 - used),
            'reset': fmt_reset(w.get('resetAt')),
        })
    updated = data.get('usage', {}).get('updatedAt') or int(time.time() * 1000)
    return {
        'provider': provider.get('displayName', 'Codex'),
        'plan': provider.get('plan', '-'),
        'model': sess.get('model', '-'),
        'runtime': sess.get('runtime', '-'),
        'context': f"{sess.get('totalTokens', 0):,} / {sess.get('contextTokens', 0):,} ({sess.get('percentUsed', 0)}%)".replace(',', '.'),
        'inputTokens': sess.get('inputTokens', 0),
        'outputTokens': sess.get('outputTokens', 0),
        'cacheRead': sess.get('cacheRead', 0),
        'windows': windows,
        'updated': datetime.fromtimestamp(updated / 1000, TZ).strftime('%Y-%m-%d %H:%M:%S'),
        'servedAt': datetime.now(TZ).strftime('%H:%M:%S'),
    }


def refresh_loop():
    global SNAPSHOT, SNAPSHOT_ERROR
    while True:
        try:
            snap = build_snapshot()
            with SNAPSHOT_LOCK:
                SNAPSHOT = snap
                SNAPSHOT_ERROR = None
        except Exception as e:
            with SNAPSHOT_LOCK:
                SNAPSHOT_ERROR = str(e)
        time.sleep(REFRESH_SECONDS)


def get_snapshot():
    with SNAPSHOT_LOCK:
        snap = SNAPSHOT
        err = SNAPSHOT_ERROR
    if snap:
        return snap
    if err:
        raise RuntimeError(err)
    return build_snapshot()


def render(s):
    cards = ''
    for w in s['windows']:
        color = '#28d6b3' if w['remaining'] > 40 else '#f5c451' if w['remaining'] > 15 else '#ff6b6b'
        cards += f'''
        <section class="card limit-card">
          <div class="label">{html.escape(w['label'])} limit</div>
          <div class="big" style="color:{color}">%{w['remaining']} kaldı</div>
          <div class="muted">Kullanılan: %{w['used']}</div>
          <div class="bar"><span style="width:{w['remaining']}%;background:{color}"></span></div>
          <div class="reset">Sıfırlanma: {html.escape(w['reset'])}</div>
        </section>'''
    return f'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
    <meta http-equiv="refresh" content="30"><meta name="color-scheme" content="dark"><meta name="theme-color" content="#050b12"><title>Codex Usage</title><link rel="icon" href="/favicon-c.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/favicon-c.svg"><style>
    *{{box-sizing:border-box}} html{{min-height:100%;background:#050b12!important;color-scheme:dark!important}} body{{min-height:100svh;margin:0!important;background:#050b12!important;background-image:radial-gradient(circle at top,#102235 0,#050b12 52%,#03070c 100%)!important;color:#e8eef7!important;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;padding:clamp(8px,2vw,18px)!important}}
    .wrap{{width:100%;max-width:980px;min-height:calc(100svh - clamp(16px,4vw,36px));margin:0 auto;display:flex;flex-direction:column;gap:14px}} h1{{font-size:clamp(34px,9vw,56px);line-height:.95;margin:0}} .sub,.muted,.reset{{color:#9daaba}} .sub{{font-size:15px;line-height:1.45}} .grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;flex:1}}
    .card{{border:1px solid rgba(40,214,179,.28)!important;background:#08101a!important;background-image:linear-gradient(180deg,rgba(13,25,40,.99),rgba(8,15,24,.99))!important;color:#e8eef7!important;border-radius:26px;padding:clamp(20px,5.4vw,34px);box-shadow:0 18px 48px rgba(0,0,0,.38)}}
    .label{{color:#9daaba;font-size:15px;text-transform:uppercase;letter-spacing:.1em}} .big{{font-size:clamp(58px,13vw,96px);line-height:.9;font-weight:900;margin:14px 0 12px;letter-spacing:-.06em}} .bar{{height:16px;border-radius:999px;background:#172434;overflow:hidden;margin:18px 0}} .bar span{{display:block;height:100%;border-radius:999px}} .reset{{font-size:16px;line-height:1.35}}
    .meta{{line-height:1.75;margin-top:auto}} .meta div{{overflow-wrap:anywhere}} code{{color:#28d6b3}}
    @media(max-width:700px){{body{{padding:5px!important}}.wrap{{min-height:calc(100svh - 10px);gap:8px}}.grid{{grid-template-columns:1fr;gap:8px}}.card{{border-radius:24px;padding:20px}}.limit-card{{min-height:30svh;display:flex;flex-direction:column;justify-content:center}}.label{{font-size:16px}}.big{{font-size:clamp(70px,21vw,104px)}}.muted,.reset{{font-size:17px}}.bar{{height:18px}}.meta{{font-size:17px;line-height:1.62;padding:18px}}h1{{font-size:clamp(42px,12vw,62px)}}.sub{{font-size:15px}}}}
    @media(max-width:420px){{.card{{padding:18px}}.limit-card{{min-height:31svh}}h1{{font-size:42px}}.big{{font-size:76px}}.meta{{font-size:16px}}}}
    </style></head><body><main class="wrap"><header><h1>Codex kullanım durumu</h1><div class="sub">Veri arka planda 30 sn’de bir güncellenir · Sayfa anında açılır · Son veri: {html.escape(s['updated'])} · Açılış: {html.escape(s.get('servedAt','-'))}</div></header><div class="grid">{cards}</div>
    <section class="card meta"><div><b>Model:</b> <code>{html.escape(str(s['model']))}</code></div><div><b>Plan:</b> {html.escape(str(s['plan']))}</div><div><b>Context:</b> {html.escape(str(s['context']))}</div><div><b>Son tur token:</b> in {s['inputTokens']:,} / out {s['outputTokens']:,} / cache {s['cacheRead']:,}</div></section>
    </main></body></html>'''


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        request_path = self.path.split('?',1)[0]
        if request_path in ('/favicon-c.svg', '/favicon.svg', '/favicon.ico'):
            self.send_response(200)
            self.send_header('Content-Type', 'image/svg+xml; charset=utf-8')
            self.send_header('Cache-Control', 'no-store, max-age=0')
            self.end_headers(); self.wfile.write(FAVICON_SVG); return
        if request_path not in ('/', SECRET_PATH):
            self.send_response(404); self.end_headers(); self.wfile.write(b'not found'); return
        try:
            body = render(get_snapshot()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers(); self.wfile.write(body)
        except Exception as e:
            body = f'Hata: {html.escape(str(e))}'.encode()
            self.send_response(500); self.end_headers(); self.wfile.write(body)
    def log_message(self, fmt, *args):
        return


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8787'))
    threading.Thread(target=refresh_loop, daemon=True).start()
    print(f'Codex usage server: http://127.0.0.1:{port}{SECRET_PATH}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
