import subprocess
import sys

# Auto-install dependencies
for _pkg in ['flask']:
    try:
        __import__(_pkg)
    except ImportError:
        print(f'Installing {_pkg}...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', _pkg],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import json
import os
import socket
from datetime import datetime
from flask import Flask, jsonify, request, Response

app = Flask(__name__)

with open('schedule.json', 'r') as _f:
    SCHEDULE_DATA = json.load(_f)

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_project_label():
    day = datetime.now().strftime('%A')
    if day in SCHEDULE_DATA['project_schedule']['MRP']:
        return 'MRP Project'
    return 'Own Project'

def resolve_title(title):
    return get_project_label() if title == 'Project' else title

def build_activities(key):
    return [
        {
            'time': a['time'],
            'title': resolve_title(a['title']),
            'duration_mins': a['duration_mins'],
        }
        for a in SCHEDULE_DATA['schedules'][key]['activities']
    ]

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return Response(HTML, mimetype='text/html')

@app.route('/api/schedule')
def api_schedule():
    key = request.args.get('type', 'home_workout')
    if key not in SCHEDULE_DATA['schedules']:
        key = 'home_workout'
    now = datetime.now()
    return jsonify({
        'activities':    build_activities(key),
        'project_label': get_project_label(),
        'date':          now.strftime('%A, %B %d %Y'),
        'day':           now.strftime('%A'),
    })

# ── HTML (single-file SPA) ────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta name="theme-color" content="#1e1e2e">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <title>Daily Schedule</title>
  <style>
    :root {
      --bg:        #1e1e2e;
      --card:      #2a2a3e;
      --card-dim:  #1c1c2c;
      --accent:    #7c3aed;
      --accent-hi: #a78bfa;
      --active-bg: #3d1f8a;
      --text:      #e2e8f0;
      --muted:     #64748b;
      --dim:       #3d4a5e;
      --green:     #22c55e;
      --red:       #ef4444;
    }

    *, *::before, *::after {
      box-sizing: border-box;
      margin: 0; padding: 0;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      min-height: 100vh;
      overscroll-behavior: none;
    }

    /* ── Header ── */
    .header {
      background: var(--card);
      padding: 14px 18px 12px;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .header h1 { font-size: 17px; font-weight: 700; letter-spacing: -.3px; }
    .header-sub { font-size: 12px; color: var(--muted); margin-top: 2px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .project-pill {
      background: rgba(34,197,94,.15);
      color: var(--green);
      font-size: 11px;
      font-weight: 600;
      padding: 1px 8px;
      border-radius: 999px;
    }

    /* ── Toggle ── */
    .toggle-row {
      display: flex;
      gap: 8px;
      padding: 12px 16px;
    }
    .tog {
      flex: 1;
      padding: 13px 8px;
      border: none;
      border-radius: 12px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: background .2s, color .2s;
      background: var(--card);
      color: var(--muted);
    }
    .tog.active { background: var(--accent); color: #fff; }

    /* ── Status card ── */
    .status-card {
      margin: 0 16px 10px;
      background: var(--card);
      border-radius: 16px;
      padding: 16px 18px;
    }
    .s-label {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.2px;
      text-transform: uppercase;
      color: var(--accent-hi);
      margin-bottom: 5px;
    }
    .s-muted {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.2px;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 4px;
    }
    #current-title {
      font-size: 18px;
      font-weight: 700;
      line-height: 1.25;
    }
    #current-until {
      font-size: 13px;
      color: var(--muted);
      margin-top: 2px;
      margin-bottom: 16px;
    }
    #countdown {
      font-size: 48px;
      font-weight: 800;
      color: var(--accent-hi);
      letter-spacing: -2px;
      font-variant-numeric: tabular-nums;
      line-height: 1;
    }
    #next-label { font-size: 12px; color: var(--muted); margin-top: 6px; }

    /* ── Notification button ── */
    .notif-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      width: calc(100% - 32px);
      margin: 0 16px 10px;
      padding: 13px 16px;
      border-radius: 12px;
      border: 1px solid rgba(124,58,237,.35);
      background: rgba(124,58,237,.1);
      color: var(--accent-hi);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: background .2s;
    }
    .notif-btn.granted { background: rgba(34,197,94,.1); color: var(--green); border-color: rgba(34,197,94,.35); }
    .notif-btn.denied  { background: rgba(239,68,68,.1);  color: var(--red);   border-color: rgba(239,68,68,.35);  cursor: default; }

    /* ── Section title ── */
    .section-head {
      padding: 4px 16px 8px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: .8px;
      text-transform: uppercase;
      color: var(--muted);
    }

    /* ── Activity list ── */
    .act-list {
      display: flex;
      flex-direction: column;
      gap: 5px;
      padding: 0 16px 32px;
    }

    .act-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 11px 14px;
      border-radius: 12px;
      background: var(--card);
      transition: background .25s, opacity .25s;
      position: relative;
      overflow: hidden;
    }
    .act-row.past {
      background: var(--card-dim);
      opacity: .45;
    }
    .act-row.active {
      background: var(--active-bg);
      box-shadow: 0 0 0 1.5px rgba(124,58,237,.55);
    }
    .act-row.active::before {
      content: '';
      position: absolute;
      left: 0; top: 50%;
      transform: translateY(-50%);
      width: 3px; height: 60%;
      background: var(--accent-hi);
      border-radius: 0 3px 3px 0;
    }

    .row-time {
      font-size: 11px;
      color: var(--muted);
      width: 92px;
      flex-shrink: 0;
      font-variant-numeric: tabular-nums;
    }
    .act-row.past   .row-time { color: var(--dim); }
    .act-row.active .row-time { color: var(--accent-hi); }

    .row-title {
      flex: 1;
      font-size: 14px;
      font-weight: 600;
    }
    .act-row.past   .row-title { color: var(--dim); }
    .act-row.active .row-title { color: #fff; }

    .row-pulse {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: var(--accent-hi);
      flex-shrink: 0;
      opacity: 0;
    }
    .act-row.active .row-pulse {
      opacity: 1;
      animation: blink 2s infinite;
    }
    @keyframes blink {
      0%,100% { opacity:1; transform:scale(1); }
      50%      { opacity:.4; transform:scale(.75); }
    }
  </style>
</head>
<body>

<!-- Header -->
<div class="header">
  <h1>Daily Schedule</h1>
  <div class="header-sub">
    <span id="date-line">—</span>
    <span class="project-pill" id="project-pill">Project →</span>
  </div>
</div>

<!-- Schedule toggle -->
<div class="toggle-row">
  <button class="tog" id="btn-home" onclick="switchSchedule('home_workout')">🏠 Home Workout</button>
  <button class="tog" id="btn-gym"  onclick="switchSchedule('gym_day')">🏋️ Gym Day</button>
</div>

<!-- Status card -->
<div class="status-card">
  <div class="s-label">Currently</div>
  <div id="current-title">—</div>
  <div id="current-until"></div>
  <div class="s-muted">Next activity in</div>
  <div id="countdown">—</div>
  <div id="next-label"></div>
</div>

<!-- Notification enable -->
<button class="notif-btn" id="notif-btn" onclick="requestNotifs()">
  <span>🔔</span> Enable Activity Notifications
</button>

<!-- Schedule list -->
<div class="section-head">Today's Schedule</div>
<div class="act-list" id="act-list">
  <div style="text-align:center;color:var(--muted);padding:24px">Loading…</div>
</div>

<script>
  // ── State ────────────────────────────────────────────────────────────────
  let schedType  = localStorage.getItem('schedType') || 'home_workout';
  let activities = [];
  let notified   = new Set();
  let didScroll  = false;

  // ── Utils ─────────────────────────────────────────────────────────────────
  function fmt12(d) {
    let h = d.getHours(), m = d.getMinutes();
    const ap = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return `${h}:${String(m).padStart(2,'0')} ${ap}`;
  }

  function parseActivities(raw) {
    const now = new Date();
    const Y = now.getFullYear(), M = now.getMonth(), D = now.getDate();
    return raw.map(a => {
      const [h, m] = a.time.split(':').map(Number);
      const start  = new Date(Y, M, D, h, m, 0);
      const end    = new Date(start.getTime() + a.duration_mins * 60000);
      return { title: a.title, start, end };
    });
  }

  // ── Load from API ─────────────────────────────────────────────────────────
  async function loadSchedule() {
    const res  = await fetch(`/api/schedule?type=${schedType}`);
    const data = await res.json();
    activities = parseActivities(data.activities);
    document.getElementById('date-line').textContent    = data.date;
    document.getElementById('project-pill').textContent = `Project → ${data.project_label}`;
    didScroll = false;
    renderList();
    setToggleUI();
  }

  function switchSchedule(type) {
    schedType = type;
    localStorage.setItem('schedType', type);
    loadSchedule();
  }

  function setToggleUI() {
    document.getElementById('btn-home').classList.toggle('active', schedType === 'home_workout');
    document.getElementById('btn-gym').classList.toggle('active', schedType === 'gym_day');
  }

  // ── Render list ───────────────────────────────────────────────────────────
  function renderList() {
    const list = document.getElementById('act-list');
    list.innerHTML = '';
    activities.forEach((act, i) => {
      const row = document.createElement('div');
      row.className = 'act-row';
      row.id = `r${i}`;
      row.innerHTML = `
        <div class="row-time">${fmt12(act.start)}</div>
        <div class="row-title">${act.title}</div>
        <div class="row-pulse"></div>`;
      list.appendChild(row);
    });
  }

  // ── Find current / next ───────────────────────────────────────────────────
  function findSlots(now) {
    let ci = -1, ni = -1;
    for (let i = 0; i < activities.length; i++) {
      if (now >= activities[i].start && now < activities[i].end) {
        ci = i;
        ni = (i + 1 < activities.length) ? i + 1 : -1;
        break;
      }
    }
    if (ci === -1) {
      for (let i = 0; i < activities.length; i++) {
        if (now < activities[i].start) { ni = i; break; }
      }
    }
    return [ci, ni];
  }

  // ── Tick (every second) ───────────────────────────────────────────────────
  function tick() {
    if (!activities.length) return;
    const now = new Date();
    const [ci, ni] = findSlots(now);

    // Current activity
    if (ci !== -1) {
      const a = activities[ci];
      document.getElementById('current-title').textContent = a.title;
      document.getElementById('current-until').textContent = `Until ${fmt12(a.end)}`;
    } else {
      document.getElementById('current-title').textContent = 'No active task right now';
      document.getElementById('current-until').textContent = '';
    }

    // Countdown
    if (ni !== -1) {
      const a   = activities[ni];
      const sec = Math.max(0, Math.floor((a.start - now) / 1000));
      const h   = Math.floor(sec / 3600);
      const m   = Math.floor((sec % 3600) / 60);
      const s   = sec % 60;
      const str = h > 0
        ? `${pad(h)}:${pad(m)}:${pad(s)}`
        : `${pad(m)}:${pad(s)}`;
      document.getElementById('countdown').textContent  = str;
      document.getElementById('next-label').textContent = `Next: ${a.title} at ${fmt12(a.start)}`;
    } else {
      document.getElementById('countdown').textContent  = '—';
      document.getElementById('next-label').textContent = 'All activities complete for today!';
    }

    // Highlight rows
    activities.forEach((_, i) => {
      const row = document.getElementById(`r${i}`);
      if (!row) return;
      row.className = 'act-row';
      if      (i === ci)              row.classList.add('active');
      else if (ci !== -1 && i < ci)  row.classList.add('past');
    });

    // Scroll active row into view once
    if (!didScroll && ci !== -1) {
      const el = document.getElementById(`r${ci}`);
      if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      didScroll = true;
    }

    // Notifications
    if (Notification.permission === 'granted') {
      activities.forEach(a => {
        const key   = a.start.getTime() + '|' + a.title;
        const delta = (a.start - now) / 1000;
        if (!notified.has(key) && delta >= -5 && delta <= 5) {
          notified.add(key);
          new Notification(`\u23F0 ${a.title}`, {
            body: `Ends at ${fmt12(a.end)}`,
            silent: false,
          });
        }
      });
    }
  }

  function pad(n) { return String(n).padStart(2, '0'); }

  // ── Notification permission ───────────────────────────────────────────────
  async function requestNotifs() {
    if (!('Notification' in window)) { alert('Notifications not supported.'); return; }
    const perm = await Notification.requestPermission();
    applyNotifUI(perm);
  }

  function applyNotifUI(perm) {
    const btn = document.getElementById('notif-btn');
    if (perm === 'granted') {
      btn.innerHTML = '<span>✅</span> Notifications Enabled';
      btn.className = 'notif-btn granted';
    } else if (perm === 'denied') {
      btn.innerHTML = '<span>🚫</span> Blocked — Enable in Browser Settings';
      btn.className = 'notif-btn denied';
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  setToggleUI();
  if ('Notification' in window) applyNotifUI(Notification.permission);

  loadSchedule().then(() => {
    tick();
    setInterval(tick, 1000);
  });
</script>
</body>
</html>
"""

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = '0.0.0.0'

    print('\n' + '=' * 48)
    print('  Daily Schedule — Web Server')
    print('=' * 48)
    print(f'  Local:   http://127.0.0.1:5000')
    print(f'  Network: http://{local_ip}:5000')
    print('  (open the Network URL on your phone)')
    print('  Press Ctrl+C to stop.')
    print('=' * 48 + '\n')

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
