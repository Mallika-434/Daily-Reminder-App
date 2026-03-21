import subprocess, sys

for _pkg, _imp in [('flask','flask'), ('google-genai','google.genai'),
                   ('python-dotenv','dotenv'), ('pillow','PIL')]:
    try: __import__(_imp)
    except ImportError:
        print(f'Installing {_pkg}...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', _pkg],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import json, os, sqlite3, threading, time, traceback
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image

load_dotenv()

MODEL      = 'gemini-2.5-flash'
DB_PATH    = 'routineai.db'
UPLOAD_DIR = Path('static/uploads')
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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
        p  = s // 12       # outer padding
        rr = s // 6        # corner radius
        img  = Image.new('RGB', (s, s), (15, 17, 23))   # #0f1117 background
        draw = Image.new('RGB', (s, s), (15, 17, 23))
        from PIL import ImageDraw as _ID
        draw = _ID.Draw(img)

        # Purple rounded rectangle
        draw.rounded_rectangle([p, p, s - p, s - p], radius=rr, fill=(124, 58, 237))

        # Three horizontal task rows with bullet dots
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

# ── DB ────────────────────────────────────────────────────────────────────────

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
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT    NOT NULL,
                start_time     TEXT    NOT NULL,
                end_time       TEXT    NOT NULL,
                snooze_minutes INTEGER DEFAULT 10,
                active         INTEGER DEFAULT 1,
                schedule_type  TEXT    DEFAULT 'home_workout',
                created_at     TEXT    DEFAULT CURRENT_TIMESTAMP
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
                date          TEXT,
                schedule_type TEXT DEFAULT 'home_workout',
                all_completed INTEGER DEFAULT 0,
                PRIMARY KEY (date, schedule_type)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        ''')
        conn.commit()


def migrate_db():
    """Safe migrations for existing databases."""
    with get_db() as conn:
        for stmt in [
            "ALTER TABLE tasks ADD COLUMN schedule_type TEXT DEFAULT 'home_workout'",
            "ALTER TABLE streak_days ADD COLUMN schedule_type TEXT DEFAULT 'home_workout'",
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)",
        ]:
            try:
                conn.execute(stmt)
                conn.commit()
            except Exception:
                pass


def get_setting(key, default=''):
    with get_db() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def set_setting(key, value):
    with get_db() as conn:
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)', (key, value))
        conn.commit()


def ensure_today_logs(schedule_type=None):
    if not schedule_type:
        schedule_type = get_setting('schedule_type', 'home_workout')
    today = date.today().isoformat()
    with get_db() as conn:
        tasks = conn.execute(
            'SELECT id FROM tasks WHERE active=1 AND schedule_type=?', (schedule_type,)
        ).fetchall()
        for t in tasks:
            if not conn.execute(
                'SELECT id FROM daily_logs WHERE task_id=? AND date=?', (t['id'], today)
            ).fetchone():
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
    with get_db() as conn:
        for stype, sdata in data['schedules'].items():
            for a in sdata['activities']:
                start  = a['time']
                end_dt = datetime.strptime(start, '%H:%M') + timedelta(minutes=a['duration_mins'])
                conn.execute(
                    'INSERT INTO tasks (name, start_time, end_time, snooze_minutes, schedule_type)'
                    ' VALUES (?,?,?,?,?)',
                    (a['title'], start, end_dt.strftime('%H:%M'), 10, stype)
                )
        conn.commit()
    print('[RoutineAI] Imported schedule.json')

# ── Streak ────────────────────────────────────────────────────────────────────

def update_streak(date_str, schedule_type=None):
    if not schedule_type:
        schedule_type = get_setting('schedule_type', 'home_workout')
    with get_db() as conn:
        logs = conn.execute('''
            SELECT l.status FROM daily_logs l JOIN tasks t ON t.id=l.task_id
            WHERE l.date=? AND t.schedule_type=? AND t.active=1
        ''', (date_str, schedule_type)).fetchall()
        if not logs:
            return
        all_done = all(r['status'] == 'completed' for r in logs)
        conn.execute(
            'INSERT OR REPLACE INTO streak_days (date, schedule_type, all_completed) VALUES (?,?,?)',
            (date_str, schedule_type, 1 if all_done else 0)
        )
        conn.commit()


def get_streak(schedule_type=None):
    if not schedule_type:
        schedule_type = get_setting('schedule_type', 'home_workout')
    with get_db() as conn:
        streak, day = 0, date.today()
        while True:
            row = conn.execute(
                'SELECT all_completed FROM streak_days WHERE date=? AND schedule_type=?',
                (day.isoformat(), schedule_type)
            ).fetchone()
            if row and row['all_completed']:
                streak += 1
                day -= timedelta(days=1)
            else:
                break
    return streak

# ── Gemini AI ─────────────────────────────────────────────────────────────────

def _client():
    key = os.environ.get('GEMINI_API_KEY', '')
    return genai.Client(api_key=key) if key else None


def _call(prompt, system=None):
    client = _client()
    if not client:
        return '(AI unavailable — add GEMINI_API_KEY to .env)'
    cfg = genai_types.GenerateContentConfig(system_instruction=system) if system else None
    try:
        kwargs = dict(model=MODEL, contents=prompt)
        if cfg:
            kwargs['config'] = cfg
        return client.models.generate_content(**kwargs).text.strip()
    except Exception as e:
        msg = str(e).lower()
        if any(x in msg for x in ('api_key', 'invalid', 'unauthorized')):
            return '(Invalid API key — check .env)'
        if any(x in msg for x in ('quota', 'rate', 'resource exhausted')):
            return '(Rate limited — try again shortly)'
        return f'(AI error: {e})'


def analyze_photo(task_name, photo_path):
    client = _client()
    if not client:
        return 7, 'AI unavailable — task marked complete!'
    try:
        img    = Image.open(photo_path)
        prompt = (
            f'The user completed: "{task_name}".\n'
            'Analyze this photo. Reply ONLY with valid JSON (no markdown):\n'
            '{"score": <1-10>, "completed": <true/false>, '
            '"feedback": "<one energetic motivational sentence>"}'
        )
        resp = client.models.generate_content(model=MODEL, contents=[prompt, img])
        raw  = resp.text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        result = json.loads(raw)
        return max(1, min(10, int(result.get('score', 7)))), result.get('feedback', 'Great work!')
    except Exception as e:
        print(f'[photo AI] {e}')
        return 7, "Task complete — you're crushing it!"


def generate_coaching(tasks_today):
    done    = [t['name'] for t in tasks_today if t['status'] == 'completed']
    missed  = [t['name'] for t in tasks_today if t['status'] == 'missed']
    pending = [t['name'] for t in tasks_today if t['status'] == 'pending']
    return _call(
        f"Time: {datetime.now().strftime('%I:%M %p')}\n"
        f"Completed ({len(done)}): {', '.join(done) or 'none'}\n"
        f"Missed ({len(missed)}): {', '.join(missed) or 'none'}\n"
        f"Pending ({len(pending)}): {', '.join(pending) or 'none'}\n\n"
        'Write a warm, specific 2-sentence coaching message to help the user stay focused.',
        system='You are RoutineAI — a supportive, energetic personal routine coach.',
    )


def suggest_reschedule(task_name, remaining):
    rem = ', '.join(f"{t['name']} at {t['start_time']}" for t in remaining) or 'none'
    return _call(
        f'Missed: "{task_name}". Remaining today: {rem}. '
        f'Time: {datetime.now().strftime("%I:%M %p")}. '
        'Suggest a 1-sentence practical reschedule plan.',
        system='You are RoutineAI — a practical schedule optimizer.',
    )


def generate_daily_summary(date_str):
    stype = get_setting('schedule_type', 'home_workout')
    with get_db() as conn:
        logs = conn.execute('''
            SELECT t.name, l.status, l.ai_score FROM daily_logs l
            JOIN tasks t ON t.id=l.task_id
            WHERE l.date=? AND t.schedule_type=? ORDER BY t.start_time
        ''', (date_str, stype)).fetchall()
    rows      = [dict(r) for r in logs]
    completed = [r for r in rows if r['status'] == 'completed']
    missed    = [r for r in rows if r['status'] == 'missed']
    avg       = round(sum(r['ai_score'] or 0 for r in completed) / len(completed), 1) if completed else 0
    return _call(
        f"Date: {date_str} | Streak: {get_streak(stype)} days\n"
        f"Done ({len(completed)}): {', '.join(r['name'] for r in completed) or 'none'}\n"
        f"Missed ({len(missed)}): {', '.join(r['name'] for r in missed) or 'none'}\n"
        f"Avg score: {avg}/10\n\n"
        'Write a 150-word daily summary: what went well, missed items, streak note, 2 tips for tomorrow.',
        system='You are RoutineAI — writing an end-of-day performance report.',
    )


def analyze_patterns():
    stype  = get_setting('schedule_type', 'home_workout')
    cutoff = (date.today() - timedelta(days=14)).isoformat()
    with get_db() as conn:
        logs = conn.execute('''
            SELECT t.name, l.status FROM daily_logs l JOIN tasks t ON t.id=l.task_id
            WHERE l.date>=? AND t.schedule_type=?
        ''', (cutoff, stype)).fetchall()
    if len(logs) < 10:
        return None
    stats = defaultdict(lambda: {'done': 0, 'missed': 0, 'total': 0})
    for r in logs:
        s = stats[r['name']]
        s['total'] += 1
        if r['status'] == 'completed': s['done'] += 1
        elif r['status'] == 'missed':  s['missed'] += 1
    stats_str = '\n'.join(f"- {n}: {s['done']}/{s['total']} done" for n, s in stats.items())
    return _call(
        f'14-day completion data:\n{stats_str}\n\n'
        'Identify 2-3 patterns and give direct, practical tips. Under 120 words.',
        system='You are RoutineAI — a data-driven behavioral coach.',
    )

# ── Background loop ───────────────────────────────────────────────────────────

_summary_done: set = set()


def _store_ai_msg(msg_type, message, date_str):
    with get_db() as conn:
        conn.execute('INSERT INTO ai_messages (type, message, date) VALUES (?,?,?)',
                     (msg_type, message, date_str))
        conn.commit()


def background_loop():
    while True:
        try:
            today    = date.today().isoformat()
            now      = datetime.now()
            now_hhmm = now.strftime('%H:%M')
            stype    = get_setting('schedule_type', 'home_workout')

            ensure_today_logs(stype)

            with get_db() as conn:
                overdue = conn.execute('''
                    SELECT l.id, t.name FROM daily_logs l JOIN tasks t ON t.id=l.task_id
                    WHERE l.date=? AND l.status='pending'
                    AND t.end_time<=? AND t.schedule_type=? AND t.active=1
                ''', (today, now_hhmm, stype)).fetchall()

                if overdue:
                    for row in overdue:
                        conn.execute("UPDATE daily_logs SET status='missed' WHERE id=?", (row['id'],))
                    conn.commit()
                    update_streak(today, stype)

                    all_logs  = [dict(r) for r in conn.execute('''
                        SELECT t.name, l.status FROM daily_logs l JOIN tasks t ON t.id=l.task_id
                        WHERE l.date=? AND t.schedule_type=?
                    ''', (today, stype)).fetchall()]
                    remaining = [dict(r) for r in conn.execute('''
                        SELECT t.name, t.start_time FROM daily_logs l JOIN tasks t ON t.id=l.task_id
                        WHERE l.date=? AND l.status='pending' AND t.schedule_type=?
                        ORDER BY t.start_time
                    ''', (today, stype)).fetchall()]

                    def _async(logs=all_logs, missed=overdue, rem=remaining, d=today):
                        _store_ai_msg('coaching', generate_coaching(logs), d)
                        for row in missed:
                            _store_ai_msg('reschedule', suggest_reschedule(row['name'], rem), d)
                    threading.Thread(target=_async, daemon=True).start()

            if now.hour == 23 and now.minute < 5 and today not in _summary_done:
                _summary_done.add(today)
                def _summary(d=today):
                    update_streak(d)
                    _store_ai_msg('summary', generate_daily_summary(d), d)
                    p = analyze_patterns()
                    if p:
                        _store_ai_msg('pattern', p, d)
                threading.Thread(target=_summary, daemon=True).start()

        except Exception:
            traceback.print_exc()
        time.sleep(60)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    ensure_today_logs()
    return render_template('index.html', public=False)


@app.route('/public')
def public_view():
    return render_template('index.html', public=True)


@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    return jsonify({'schedule_type': get_setting('schedule_type', 'home_workout')})


@app.route('/api/settings', methods=['POST'])
def api_save_settings():
    d = request.json or {}
    if d.get('schedule_type') in ('home_workout', 'gym_day'):
        set_setting('schedule_type', d['schedule_type'])
        ensure_today_logs(d['schedule_type'])
    return jsonify({'ok': True})


@app.route('/api/today')
def api_today():
    schedule = request.args.get('schedule', get_setting('schedule_type', 'home_workout'))
    today    = date.today().isoformat()
    ensure_today_logs(schedule)

    with get_db() as conn:
        rows = conn.execute('''
            SELECT l.id, l.task_id, l.status, l.completed_at, l.photo_path,
                   l.ai_score, l.ai_feedback, l.snooze_until,
                   t.name, t.start_time, t.end_time, t.snooze_minutes
            FROM daily_logs l JOIN tasks t ON t.id=l.task_id
            WHERE l.date=? AND t.active=1 AND t.schedule_type=?
            ORDER BY t.start_time
        ''', (today, schedule)).fetchall()

        ai_msg = conn.execute(
            'SELECT type, message, created_at FROM ai_messages WHERE date=? ORDER BY id DESC LIMIT 1',
            (today,)
        ).fetchone()

        avg_row = conn.execute(
            'SELECT ROUND(AVG(l.ai_score),1) FROM daily_logs l JOIN tasks t ON t.id=l.task_id '
            'WHERE l.ai_score IS NOT NULL AND t.schedule_type=?',
            (schedule,)
        ).fetchone()

        mon = (date.today() - timedelta(days=date.today().weekday())).isoformat()
        sun = (date.today() + timedelta(days=6 - date.today().weekday())).isoformat()
        wtotal = conn.execute(
            'SELECT COUNT(*) FROM daily_logs l JOIN tasks t ON t.id=l.task_id '
            'WHERE l.date>=? AND l.date<=? AND t.schedule_type=? AND t.active=1',
            (mon, sun, schedule)
        ).fetchone()[0]
        wdone = conn.execute(
            "SELECT COUNT(*) FROM daily_logs l JOIN tasks t ON t.id=l.task_id "
            "WHERE l.date>=? AND l.date<=? AND t.schedule_type=? AND t.active=1 AND l.status='completed'",
            (mon, sun, schedule)
        ).fetchone()[0]

    tasks     = [dict(r) for r in rows]
    completed = sum(1 for t in tasks if t['status'] == 'completed')
    total     = len(tasks)

    # Identify current and next task
    now_hhmm = datetime.now().strftime('%H:%M')
    current_task = next_task = None
    for i, t in enumerate(tasks):
        if t['start_time'] <= now_hhmm < t['end_time']:
            current_task = t
            if i + 1 < len(tasks):
                next_task = {'name': tasks[i+1]['name'], 'start_time': tasks[i+1]['start_time']}
            break
        elif t['start_time'] > now_hhmm and next_task is None:
            next_task = {'name': t['name'], 'start_time': t['start_time']}

    return jsonify({
        'date':         today,
        'tasks':        tasks,
        'streak':       get_streak(schedule),
        'completed':    completed,
        'total':        total,
        'avg_score':    avg_row[0] or 0.0,
        'weekly_pct':   round(wdone / wtotal * 100) if wtotal else 0,
        'ai_message':   dict(ai_msg) if ai_msg else None,
        'current_task': current_task,
        'next_task':    next_task,
    })


@app.route('/api/weekly')
def api_weekly():
    schedule = request.args.get('schedule', get_setting('schedule_type', 'home_workout'))
    today    = date.today()
    monday   = today - timedelta(days=today.weekday())
    result   = []
    with get_db() as conn:
        for i in range(7):
            d     = monday + timedelta(days=i)
            d_str = d.isoformat()
            total = conn.execute(
                'SELECT COUNT(*) FROM daily_logs l JOIN tasks t ON t.id=l.task_id '
                'WHERE l.date=? AND t.schedule_type=? AND t.active=1',
                (d_str, schedule)
            ).fetchone()[0]
            done = conn.execute(
                "SELECT COUNT(*) FROM daily_logs l JOIN tasks t ON t.id=l.task_id "
                "WHERE l.date=? AND t.schedule_type=? AND t.active=1 AND l.status='completed'",
                (d_str, schedule)
            ).fetchone()[0]
            result.append({
                'day':      d.strftime('%a'),
                'date':     d_str,
                'pct':      round(done / total * 100) if total else 0,
                'done':     done,
                'total':    total,
                'is_today': d == today,
            })
    return jsonify(result)


@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    schedule = request.args.get('schedule', get_setting('schedule_type', 'home_workout'))
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM tasks WHERE active=1 AND schedule_type=? ORDER BY start_time',
            (schedule,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/tasks', methods=['POST'])
def api_create_task():
    d = request.json or {}
    if not all(d.get(k) for k in ('name', 'start_time', 'end_time')):
        return jsonify({'error': 'name, start_time, end_time required'}), 400
    stype = d.get('schedule_type', get_setting('schedule_type', 'home_workout'))
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO tasks (name, start_time, end_time, snooze_minutes, schedule_type) VALUES (?,?,?,?,?)',
            (d['name'], d['start_time'], d['end_time'], int(d.get('snooze_minutes', 10)), stype)
        )
        task_id = cur.lastrowid
        conn.execute('INSERT INTO daily_logs (task_id, date, status) VALUES (?,?,?)',
                     (task_id, date.today().isoformat(), 'pending'))
        conn.commit()
    return jsonify({'ok': True, 'id': task_id})


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def api_update_task(task_id):
    d = request.json or {}
    with get_db() as conn:
        conn.execute(
            'UPDATE tasks SET name=?, start_time=?, end_time=?, snooze_minutes=? WHERE id=?',
            (d['name'], d['start_time'], d['end_time'], int(d.get('snooze_minutes', 10)), task_id)
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
        Image.open(str(fpath)).verify()
    except Exception:
        fpath.unlink(missing_ok=True)
        return jsonify({'error': 'invalid image'}), 400

    with get_db() as conn:
        row = conn.execute(
            'SELECT t.name FROM daily_logs l JOIN tasks t ON t.id=l.task_id WHERE l.id=?',
            (log_id,)
        ).fetchone()
    if not row:
        return jsonify({'error': 'not found'}), 404

    task_name = row['name']
    with get_db() as conn:
        conn.execute(
            "UPDATE daily_logs SET status='completed', completed_at=?, photo_path=? WHERE id=?",
            (datetime.now().isoformat(), f'uploads/{fname}', log_id)
        )
        conn.commit()

    def _analyze(tid=log_id, name=task_name, path=str(fpath), d=date.today().isoformat()):
        score, feedback = analyze_photo(name, path)
        with get_db() as c:
            c.execute('UPDATE daily_logs SET ai_score=?, ai_feedback=? WHERE id=?',
                      (score, feedback, tid))
            c.commit()
        update_streak(d)
        _store_ai_msg('feedback', f'{name} ({score}/10): {feedback}', d)
    threading.Thread(target=_analyze, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/api/complete-simple/<int:log_id>', methods=['POST'])
def api_complete_simple(log_id):
    with get_db() as conn:
        if not conn.execute('SELECT id FROM daily_logs WHERE id=?', (log_id,)).fetchone():
            return jsonify({'error': 'not found'}), 404
        conn.execute(
            "UPDATE daily_logs SET status='completed', completed_at=? WHERE id=?",
            (datetime.now().isoformat(), log_id)
        )
        conn.commit()
    update_streak(date.today().isoformat())
    return jsonify({'ok': True})


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
            "UPDATE daily_logs SET status='snoozed', snooze_until=? WHERE id=?", (until, log_id)
        )
        conn.commit()
    return jsonify({'ok': True, 'snooze_until': until})


@app.route('/api/insights')
def api_insights():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM ai_messages ORDER BY id DESC LIMIT 30').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/trigger-summary', methods=['POST'])
def api_trigger_summary():
    today = date.today().isoformat()
    def _run(d=today):
        _store_ai_msg('summary', generate_daily_summary(d), d)
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/api/generate-coaching', methods=['POST'])
def api_generate_coaching():
    stype = get_setting('schedule_type', 'home_workout')
    today = date.today().isoformat()
    with get_db() as conn:
        rows = conn.execute('''
            SELECT t.name, l.status FROM daily_logs l JOIN tasks t ON t.id=l.task_id
            WHERE l.date=? AND t.schedule_type=?
        ''', (today, stype)).fetchall()
    tasks_today = [dict(r) for r in rows]
    def _run(tasks=tasks_today, d=today):
        _store_ai_msg('coaching', generate_coaching(tasks), d)
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/sw.js')
def serve_sw():
    """Serve the service worker from the root path so its scope covers the whole app."""
    from flask import make_response
    resp = make_response(send_from_directory('static', 'sw.js'))
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.route('/static/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory('static/uploads', filename)

# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import socket
    init_db()
    migrate_db()
    import_schedule_json()
    ensure_today_logs()
    generate_pwa_icons()
    threading.Thread(target=background_loop, daemon=True).start()

    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = '127.0.0.1'

    port = int(os.environ.get('PORT', 5000))
    print('\n' + '=' * 54)
    print('  RoutineAI — Professional Routine Dashboard')
    print('=' * 54)
    print(f'  Local:   http://127.0.0.1:{port}')
    print(f'  Network: http://{local_ip}:{port}')
    print(f'  Public:  http://{local_ip}:{port}/public')
    print(f'  Model:   {MODEL}')
    print('=' * 54 + '\n')
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
