import subprocess, sys

for _pkg, _imp in [('flask', 'flask'), ('pillow', 'PIL'), ('requests', 'requests')]:
    try: __import__(_imp)
    except ImportError:
        print(f'Installing {_pkg}...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', _pkg],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import os
from pathlib import Path

import requests as http

from flask import Flask, jsonify, make_response, render_template, request, send_from_directory
from PIL import Image

GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent'

app = Flask(__name__)

# ── PWA icon generator ────────────────────────────────────────────────────────

def generate_pwa_icons():
    """Generate 192x192 and 512x512 PNG icons for the PWA manifest."""
    icon_dir = Path('static/icons')
    icon_dir.mkdir(parents=True, exist_ok=True)

    for size in [192, 512]:
        out = icon_dir / f'icon-{size}x{size}.png'
        if out.exists():
            continue
        s  = size
        p  = s // 12
        rr = s // 6
        img  = Image.new('RGB', (s, s), (15, 17, 23))
        from PIL import ImageDraw as _ID
        draw = _ID.Draw(img)

        draw.rounded_rectangle([p, p, s - p, s - p], radius=rr, fill=(124, 58, 237))

        dot_r  = max(5, s // 22)
        line_h = max(3, s // 38)
        dot_x  = s // 4 + dot_r
        lx     = dot_x + dot_r * 2 + s // 20
        rx     = s * 3 // 4

        dot_colors  = [(245, 158, 11), (180, 165, 240), (160, 148, 215)]
        line_colors = [(255, 255, 255), (200, 188, 255), (180, 165, 240)]

        for i in range(3):
            cy = int(s * 0.35) + i * (s // 5)
            draw.ellipse([dot_x - dot_r, cy - dot_r, dot_x + dot_r, cy + dot_r],
                         fill=dot_colors[i])
            lh2 = line_h // 2
            draw.rounded_rectangle([lx, cy - lh2, rx, cy + lh2 + (line_h % 2)],
                                   radius=lh2, fill=line_colors[i])

        img.save(str(out), 'PNG')
        print(f'[RoutineAI] Icon generated: {out.name}')

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/gemini', methods=['POST'])
def api_gemini():
    prompt = (request.json or {}).get('prompt', '').strip()
    if not prompt:
        return jsonify({'error': 'prompt is required'}), 400

    key = os.environ.get('GEMINI_API_KEY', '')
    if not key:
        return jsonify({'error': 'GEMINI_API_KEY not configured on server'}), 503

    try:
        resp = http.post(
            GEMINI_URL,
            params={'key': key},
            json={'contents': [{'parts': [{'text': prompt}]}]},
            timeout=30,
        )
        data = resp.json()
        if not resp.ok:
            msg = data.get('error', {}).get('message', resp.text)
            return jsonify({'error': msg}), resp.status_code
        text = data['candidates'][0]['content']['parts'][0]['text']
        return jsonify({'text': text.strip()})
    except Exception as e:
        return jsonify({'error': str(e)}), 502


@app.route('/sw.js')
def serve_sw():
    """Serve the service worker from root path so its scope covers the whole app."""
    resp = make_response(send_from_directory('static', 'sw.js'))
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import socket
    generate_pwa_icons()

    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = '127.0.0.1'

    port = int(os.environ.get('PORT', 5000))
    print('\n' + '=' * 54)
    print('  RoutineAI — Daily Routine Dashboard')
    print('=' * 54)
    print(f'  Local:   http://127.0.0.1:{port}')
    print(f'  Network: http://{local_ip}:{port}')
    print('=' * 54 + '\n')
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
