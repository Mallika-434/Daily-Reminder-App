import subprocess
import sys

# ── Auto-install ──────────────────────────────────────────────────────────────
for _pkg, _imp in [('flask','flask'), ('google-genai','google.genai'),
                   ('python-dotenv','dotenv'), ('pillow','PIL')]:
    try:
        __import__(_imp)
    except ImportError:
        print(f'Installing {_pkg}...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', _pkg],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import json
import os
import sqlite3
import threading
import time
import traceback
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
MODEL      = 'gemini-1.5-flash'
DB_PATH    = 'routineai.db'
UPLOAD_DIR = Path('static/uploads')
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    NOT NULL,
                start_time      TEXT    NOT NULL,
                end_time        TEXT    NOT NULL,
                snooze_minutes  INTEGER DEFAULT 10,
                active          INTEGER DEFAULT 1,
                created_at      TEXT    DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS daily_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id      INTEGER NOT NULL,
                date         TEXT    NOT NULL,
                status       TEXT    DEFAULT 'pending',
                completed_at TEXT,
                photo_path   TEXT,
                ai_score     INTEGER,
                ai_feedback  TEXT,
                snooze_until TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );
            CREATE TABLE IF NOT EXISTS ai_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                type       TEXT,
                message    TEXT,
                date       TEXT
            );
            CREATE TABLE IF NOT EXISTS streak_days (
                date          TEXT PRIMARY KEY,
                all_completed INTEGER DEFAULT 0
            );
        ''')
        conn.commit()


def ensure_today_logs():
    today = date.today().isoformat()
    with get_db() as conn:
        tasks = conn.execute('SELECT id FROM tasks WHERE active=1').fetchall()
        for t in tasks:
            exists = conn.execute(
                'SELECT id FROM daily_logs WHERE task_id=? AND date=?',
                (t['id'], today)
            ).fetchone()
            if not exists:
                conn.execute(
                    'INSERT INTO daily_logs (task_id, date, status) VALUES (?,?,?)',
                    (t['id'], today, 'pending')
                )
        conn.commit()


def import_schedule_json():
    path = Path('schedule.json')
    if not path.exists():
        return
    with get_db() as conn:
        if conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] > 0:
            return
    with open(path) as f:
        data = json.load(f)
    activities = data['schedules']['home_workout']['activities']
    with get_db() as conn:
        for a in activities:
            start = a['time']
            end_dt = datetime.strptime(start, '%H:%M') + timedelta(minutes=a['duration_mins'])
            conn.execute(
                'INSERT INTO tasks (name, start_time, end_time, snooze_minutes) VALUES (?,?,?,?)',
                (a['title'], start, end_dt.strftime('%H:%M'), 10)
            )
        conn.commit()
    print('[RoutineAI] Imported schedule.json as default tasks.')

# ── Streak ────────────────────────────────────────────────────────────────────

def update_streak(date_str):
    with get_db() as conn:
        logs = conn.execute(
            'SELECT status FROM daily_logs WHERE date=?', (date_str,)
        ).fetchall()
        if not logs:
            return
        all_done = all(r['status'] == 'completed' for r in logs)
        conn.execute(
            'INSERT OR REPLACE INTO streak_days (date, all_completed) VALUES (?,?)',
            (date_str, 1 if all_done else 0)
        )
        conn.commit()


def get_streak():
    with get_db() as conn:
        streak = 0
        day = date.today()
        while True:
            row = conn.execute(
                'SELECT all_completed FROM streak_days WHERE date=?',
                (day.isoformat(),)
            ).fetchone()
            if row and row['all_completed']:
                streak += 1
                day -= timedelta(days=1)
            else:
                break
        return streak

# ── Gemini AI helpers ─────────────────────────────────────────────────────────

def _client():
    """Return a configured Gemini client, or None if key is missing."""
    key = os.environ.get('GEMINI_API_KEY', '')
    if not key:
        return None
    return genai.Client(api_key=key)


def _call(prompt: str, system: str = None) -> str:
    client = _client()
    if not client:
        return '(AI unavailable — add GEMINI_API_KEY to .env)'
    cfg = genai_types.GenerateContentConfig(
        system_instruction=system
    ) if system else None
    try:
        kwargs = dict(model=MODEL, contents=prompt)
        if cfg:
            kwargs['config'] = cfg
        resp = client.models.generate_content(**kwargs)
        return resp.text.strip()
    except Exception as e:
        msg = str(e).lower()
        if 'api_key' in msg or 'invalid' in msg or 'unauthorized' in msg:
            return '(Invalid API key — check .env)'
        if 'quota' in msg or 'rate' in msg or 'resource exhausted' in msg:
            return '(Rate limited — try again shortly)'
        return f'(AI error: {e})'


def analyze_photo(task_name: str, photo_path: str):
    """Return (score:int, feedback:str) for a completion photo."""
    client = _client()
    if not client:
        return 7, 'AI unavailable — task marked complete!'
    try:
        img    = Image.open(photo_path)
        prompt = (
            f'The user completed their task: "{task_name}".\n'
            'Look at this photo. Did they actually complete it?\n'
            'Reply ONLY with valid JSON (no markdown):\n'
            '{"score": <1-10>, "completed": <true/false>, '
            '"feedback": "<one energetic motivational sentence>"}'
        )
        resp = client.models.generate_content(
            model=MODEL,
            contents=[prompt, img],
        )
        raw = resp.text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        result   = json.loads(raw)
        score    = max(1, min(10, int(result.get('score', 7))))
        feedback = result.get('feedback', 'Great work — keep it up!')
        return score, feedback
    except Exception as e:
        print(f'[photo AI error] {e}')
        return 7, "Task complete — you're crushing it!"


def generate_coaching(tasks_today: list):
    done    = [t['name'] for t in tasks_today if t['status'] == 'completed']
    missed  = [t['name'] for t in tasks_today if t['status'] == 'missed']
    pending = [t['name'] for t in tasks_today if t['status'] == 'pending']
    prompt  = (
        f"Current time: {datetime.now().strftime('%I:%M %p')}\n"
        f"Completed ({len(done)}): {', '.join(done) or 'none'}\n"
        f"Missed ({len(missed)}): {', '.join(missed) or 'none'}\n"
        f"Still pending ({len(pending)}): {', '.join(pending) or 'none'}\n\n"
        'Write a warm, specific 2-sentence coaching message to help the user refocus.'
    )
    return _call(
        prompt,
        system='You are RoutineAI — a supportive, energetic personal routine coach.',
    )


def suggest_reschedule(task_name: str, remaining: list):
    remaining_str = ', '.join(
        f"{t['name']} at {t['start_time']}" for t in remaining
    ) or 'none'
    prompt = (
        f'Missed task: "{task_name}".\n'
        f'Remaining today: {remaining_str}\n'
        f'Current time: {datetime.now().strftime("%I:%M %p")}\n'
        'Suggest a practical 1-sentence reschedule plan.'
    )
    return _call(
        prompt,
        system='You are RoutineAI — a practical schedule optimizer.',
    )


def generate_daily_summary(date_str: str):
    with get_db() as conn:
        logs = conn.execute('''
            SELECT t.name, l.status, l.ai_score, t.start_time
            FROM daily_logs l JOIN tasks t ON t.id = l.task_id
            WHERE l.date = ? ORDER BY t.start_time
        ''', (date_str,)).fetchall()
    rows      = [dict(r) for r in logs]
    completed = [r for r in rows if r['status'] == 'completed']
    missed    = [r for r in rows if r['status'] == 'missed']
    avg_score = (
        round(sum(r['ai_score'] or 0 for r in completed) / len(completed), 1)
        if completed else 0
    )
    prompt = (
        f"Date: {date_str} | Streak: {get_streak()} days\n"
        f"Completed ({len(completed)}): {', '.join(r['name'] for r in completed) or 'none'}\n"
        f"Missed ({len(missed)}): {', '.join(r['name'] for r in missed) or 'none'}\n"
        f"Avg AI score: {avg_score}/10\n\n"
        'Write a 150-word daily summary: what went well, what was missed, '
        'streak note, and 2 specific tips for tomorrow.'
    )
    return _call(
        prompt,
        system='You are RoutineAI — writing an end-of-day performance report.',
    )


def analyze_patterns():
    cutoff = (date.today() - timedelta(days=14)).isoformat()
    with get_db() as conn:
        logs = conn.execute('''
            SELECT t.name, l.status FROM daily_logs l
            JOIN tasks t ON t.id = l.task_id
            WHERE l.date >= ?
        ''', (cutoff,)).fetchall()
    if len(logs) < 10:
        return None
    stats = defaultdict(lambda: {'completed': 0, 'missed': 0, 'total': 0})
    for r in logs:
        s = stats[r['name']]
        s['total'] += 1
        if r['status'] == 'completed':
            s['completed'] += 1
        elif r['status'] == 'missed':
            s['missed'] += 1
    stats_str = '\n'.join(
        f"- {name}: {s['completed']}/{s['total']} done ({s['missed']} missed)"
        for name, s in stats.items()
    )
    prompt = (
        f'Last 14 days completion data:\n{stats_str}\n\n'
        'Identify 2-3 patterns and give direct, practical tips. Under 120 words.'
    )
    return _call(
        prompt,
        system='You are RoutineAI — a data-driven behavioral coach.',
    )

# ── Background thread ─────────────────────────────────────────────────────────
_summary_done: set = set()


def _store_ai_msg(msg_type: str, message: str, date_str: str):
    with get_db() as conn:
        conn.execute(
            'INSERT INTO ai_messages (type, message, date) VALUES (?,?,?)',
            (msg_type, message, date_str)
        )
        conn.commit()


def background_loop():
    while True:
        try:
            today    = date.today().isoformat()
            now      = datetime.now()
            now_hhmm = now.strftime('%H:%M')

            ensure_today_logs()

            # Mark overdue pending tasks as missed
            with get_db() as conn:
                overdue = conn.execute('''
                    SELECT l.id, t.name, l.task_id
                    FROM daily_logs l JOIN tasks t ON t.id = l.task_id
                    WHERE l.date=? AND l.status='pending' AND t.end_time <= ?
                ''', (today, now_hhmm)).fetchall()

                if overdue:
                    for row in overdue:
                        conn.execute(
                            "UPDATE daily_logs SET status='missed' WHERE id=?",
                            (row['id'],)
                        )
                    conn.commit()
                    update_streak(today)

                    # Coaching message in background thread
                    all_logs = [dict(r) for r in conn.execute('''
                        SELECT t.name, l.status FROM daily_logs l
                        JOIN tasks t ON t.id = l.task_id WHERE l.date=?
                    ''', (today,)).fetchall()]

                    # Reschedule suggestion for each newly missed task
                    remaining = [dict(r) for r in conn.execute('''
                        SELECT t.name, t.start_time FROM daily_logs l
                        JOIN tasks t ON t.id = l.task_id
                        WHERE l.date=? AND l.status='pending'
                        ORDER BY t.start_time
                    ''', (today,)).fetchall()]

                    def _async_coaching(logs=all_logs, missed=overdue,
                                        rem=remaining, d=today):
                        msg = generate_coaching(logs)
                        _store_ai_msg('coaching', msg, d)
                        for row in missed:
                            rs = suggest_reschedule(row['name'], rem)
                            _store_ai_msg('reschedule', rs, d)
                    threading.Thread(target=_async_coaching, daemon=True).start()

            # Daily summary at 23:00–23:04
            if now.hour == 23 and now.minute < 5 and today not in _summary_done:
                _summary_done.add(today)

                def _async_summary(d=today):
                    update_streak(d)
                    summary = generate_daily_summary(d)
                    _store_ai_msg('summary', summary, d)
                    pattern = analyze_patterns()
                    if pattern:
                        _store_ai_msg('pattern', pattern, d)
                threading.Thread(target=_async_summary, daemon=True).start()

        except Exception:
            traceback.print_exc()

        time.sleep(60)

# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    ensure_today_logs()
    return render_template('index.html')


@app.route('/api/today')
def api_today():
    today = date.today().isoformat()
    ensure_today_logs()
    with get_db() as conn:
        rows = conn.execute('''
            SELECT l.id, l.task_id, l.status, l.completed_at, l.photo_path,
                   l.ai_score, l.ai_feedback, l.snooze_until,
                   t.name, t.start_time, t.end_time, t.snooze_minutes
            FROM daily_logs l JOIN tasks t ON t.id = l.task_id
            WHERE l.date=? AND t.active=1
            ORDER BY t.start_time
        ''', (today,)).fetchall()

        ai_msg = conn.execute(
            'SELECT type, message FROM ai_messages WHERE date=? ORDER BY id DESC LIMIT 1',
            (today,)
        ).fetchone()

    tasks     = [dict(r) for r in rows]
    completed = sum(1 for t in tasks if t['status'] == 'completed')
    total     = len(tasks)
    return jsonify({
        'date':       today,
        'tasks':      tasks,
        'streak':     get_streak(),
        'progress':   round(completed / total * 100) if total else 0,
        'completed':  completed,
        'total':      total,
        'ai_message': dict(ai_msg) if ai_msg else None,
    })


@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM tasks WHERE active=1 ORDER BY start_time'
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/tasks', methods=['POST'])
def api_create_task():
    d = request.json or {}
    if not all(d.get(k) for k in ('name', 'start_time', 'end_time')):
        return jsonify({'error': 'name, start_time, end_time required'}), 400
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO tasks (name, start_time, end_time, snooze_minutes) VALUES (?,?,?,?)',
            (d['name'], d['start_time'], d['end_time'], int(d.get('snooze_minutes', 10)))
        )
        task_id = cur.lastrowid
        conn.execute(
            'INSERT INTO daily_logs (task_id, date, status) VALUES (?,?,?)',
            (task_id, date.today().isoformat(), 'pending')
        )
        conn.commit()
    return jsonify({'ok': True, 'id': task_id})


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def api_update_task(task_id):
    d = request.json or {}
    with get_db() as conn:
        conn.execute(
            'UPDATE tasks SET name=?, start_time=?, end_time=?, snooze_minutes=? WHERE id=?',
            (d['name'], d['start_time'], d['end_time'],
             int(d.get('snooze_minutes', 10)), task_id)
        )
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    with get_db() as conn:
        conn.execute('UPDATE tasks SET active=0 WHERE id=?', (task_id,))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/complete/<int:log_id>', methods=['POST'])
def api_complete(log_id):
    if 'photo' not in request.files or not request.files['photo'].filename:
        return jsonify({'error': 'photo required'}), 400

    photo = request.files['photo']
    ext   = Path(photo.filename).suffix.lower() or '.jpg'
    fname = f'{log_id}_{int(time.time())}{ext}'
    fpath = UPLOAD_DIR / fname
    photo.save(str(fpath))

    try:
        img = Image.open(str(fpath))
        img.verify()
    except Exception:
        fpath.unlink(missing_ok=True)
        return jsonify({'error': 'invalid image file'}), 400

    with get_db() as conn:
        row = conn.execute(
            'SELECT t.name FROM daily_logs l JOIN tasks t ON t.id=l.task_id WHERE l.id=?',
            (log_id,)
        ).fetchone()
    if not row:
        return jsonify({'error': 'log not found'}), 404
    task_name = row['name']

    # Mark complete immediately so the UI updates
    now_iso = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE daily_logs SET status='completed', completed_at=?, photo_path=? WHERE id=?",
            (now_iso, f'uploads/{fname}', log_id)
        )
        conn.commit()

    # AI photo analysis runs in background
    def _analyze(tid=log_id, name=task_name, path=str(fpath), d=date.today().isoformat()):
        score, feedback = analyze_photo(name, path)
        with get_db() as c:
            c.execute(
                'UPDATE daily_logs SET ai_score=?, ai_feedback=? WHERE id=?',
                (score, feedback, tid)
            )
            c.commit()
        update_streak(d)
        _store_ai_msg('feedback',
                      f'{name} ({score}/10): {feedback}', d)
    threading.Thread(target=_analyze, daemon=True).start()

    return jsonify({'ok': True, 'message': 'Photo received — Gemini is reviewing it!'})


@app.route('/api/snooze/<int:log_id>', methods=['POST'])
def api_snooze(log_id):
    with get_db() as conn:
        row = conn.execute(
            'SELECT t.snooze_minutes FROM daily_logs l JOIN tasks t ON t.id=l.task_id WHERE l.id=?',
            (log_id,)
        ).fetchone()
        if not row:
            return jsonify({'error': 'not found'}), 404
        until = (datetime.now() + timedelta(minutes=row['snooze_minutes'])).strftime('%H:%M')
        conn.execute(
            "UPDATE daily_logs SET status='snoozed', snooze_until=? WHERE id=?",
            (until, log_id)
        )
        conn.commit()
    return jsonify({'ok': True, 'snooze_until': until})


@app.route('/api/insights')
def api_insights():
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM ai_messages ORDER BY id DESC LIMIT 30'
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/trigger-summary', methods=['POST'])
def api_trigger_summary():
    today = date.today().isoformat()
    def _run(d=today):
        summary = generate_daily_summary(d)
        _store_ai_msg('summary', summary, d)
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/static/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory('static/uploads', filename)

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import socket

    init_db()
    import_schedule_json()
    ensure_today_logs()

    threading.Thread(target=background_loop, daemon=True).start()

    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = '127.0.0.1'

    port = int(os.environ.get('PORT', 5000))
    print('\n' + '=' * 52)
    print('  RoutineAI — AI-Powered Personal Routine')
    print('=' * 52)
    print(f'  Local:   http://127.0.0.1:{port}')
    print(f'  Network: http://{local_ip}:{port}')
    print(f'  Model:   {MODEL}')
    print('=' * 52 + '\n')

    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
