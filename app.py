import subprocess
import sys

# Auto-install required libraries
_required = ['plyer']
for _pkg in _required:
    try:
        __import__(_pkg)
    except ImportError:
        print(f'Installing {_pkg}...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', _pkg],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import json
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
import threading
from plyer import notification

# ── Load schedule data ────────────────────────────────────────────────────────
with open('schedule.json', 'r') as _f:
    SCHEDULE_DATA = json.load(_f)

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_project_label():
    day = datetime.now().strftime('%A')
    if day in SCHEDULE_DATA['project_schedule']['MRP']:
        return 'MRP Project'
    return 'Own Project'


def resolve_title(title):
    if title == 'Project':
        return get_project_label()
    return title


def parse_time_today(time_str):
    t = datetime.strptime(time_str, '%H:%M')
    now = datetime.now()
    return t.replace(year=now.year, month=now.month, day=now.day)


def build_activities(schedule_key):
    raw = SCHEDULE_DATA['schedules'][schedule_key]['activities']
    result = []
    for a in raw:
        start = parse_time_today(a['time'])
        end = start + timedelta(minutes=a['duration_mins'])
        result.append({'start': start, 'end': end, 'title': resolve_title(a['title'])})
    return result


# ── Colours ───────────────────────────────────────────────────────────────────
C = {
    'bg':       '#1e1e2e',
    'card':     '#2a2a3e',
    'card_dim': '#1a1a2e',
    'accent':   '#7c3aed',
    'accent_hi':'#a78bfa',
    'active_bg':'#3d1f8a',
    'text':     '#e2e8f0',
    'muted':    '#64748b',
    'dim':      '#4a5568',
    'green':    '#22c55e',
    'red':      '#ef4444',
}


# ── Main App ──────────────────────────────────────────────────────────────────
class ReminderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('Daily Schedule Reminder')
        self.root.configure(bg=C['bg'])
        self.root.geometry('720x780')
        self.root.minsize(560, 600)

        self.schedule_key = 'home_workout'
        self.running = False
        self.notified: set = set()
        self.activities: list = []
        self.activity_frames: list = []

        self._build_ui()
        self._load_and_render()
        self._tick()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_toggle()
        self._build_info_strip()
        self._build_status_card()
        self._build_schedule_list()
        self._build_controls()

    def _build_header(self):
        f = tk.Frame(self.root, bg=C['bg'])
        f.pack(fill='x', pady=(18, 4))
        tk.Label(f, text='Daily Schedule Reminder',
                 font=('Segoe UI', 20, 'bold'), fg=C['text'], bg=C['bg']).pack()

    def _build_toggle(self):
        f = tk.Frame(self.root, bg=C['bg'])
        f.pack(pady=6)

        tk.Label(f, text='Schedule Type:', font=('Segoe UI', 10),
                 fg=C['muted'], bg=C['bg']).pack(side='left', padx=8)

        self.btn_home = tk.Button(
            f, text='Home Workout Day',
            command=lambda: self._switch_schedule('home_workout'),
            font=('Segoe UI', 10, 'bold'), bg=C['accent'], fg='white',
            relief='flat', padx=14, pady=6, cursor='hand2',
            activebackground='#6d28d9', activeforeground='white', bd=0)
        self.btn_home.pack(side='left', padx=4)

        self.btn_gym = tk.Button(
            f, text='Gym Day',
            command=lambda: self._switch_schedule('gym_day'),
            font=('Segoe UI', 10, 'bold'), bg=C['card'], fg=C['muted'],
            relief='flat', padx=14, pady=6, cursor='hand2',
            activebackground='#3a3a5e', activeforeground=C['text'], bd=0)
        self.btn_gym.pack(side='left', padx=4)

    def _build_info_strip(self):
        f = tk.Frame(self.root, bg=C['card'])
        f.pack(fill='x', padx=20, pady=(8, 0))

        self.lbl_day = tk.Label(f, text='', font=('Segoe UI', 10),
                                fg=C['muted'], bg=C['card'])
        self.lbl_day.pack(side='left', padx=14, pady=8)

        self.lbl_project = tk.Label(f, text='', font=('Segoe UI', 10, 'bold'),
                                    fg=C['green'], bg=C['card'])
        self.lbl_project.pack(side='right', padx=14, pady=8)

    def _build_status_card(self):
        f = tk.Frame(self.root, bg=C['card'])
        f.pack(fill='x', padx=20, pady=(4, 8))

        inner = tk.Frame(f, bg=C['card'], pady=14, padx=16)
        inner.pack(fill='x')

        tk.Label(inner, text='NOW', font=('Segoe UI', 8, 'bold'),
                 fg=C['accent'], bg=C['card']).pack(anchor='w')

        self.lbl_current = tk.Label(inner, text='—',
            font=('Segoe UI', 15, 'bold'), fg=C['text'], bg=C['card'],
            wraplength=640, justify='left')
        self.lbl_current.pack(anchor='w', pady=(2, 10))

        tk.Label(inner, text='NEXT ACTIVITY IN', font=('Segoe UI', 8, 'bold'),
                 fg=C['muted'], bg=C['card']).pack(anchor='w')

        self.lbl_countdown = tk.Label(inner, text='—',
            font=('Segoe UI', 30, 'bold'), fg=C['accent'], bg=C['card'])
        self.lbl_countdown.pack(anchor='w')

        self.lbl_next = tk.Label(inner, text='',
            font=('Segoe UI', 10), fg=C['muted'], bg=C['card'])
        self.lbl_next.pack(anchor='w')

    def _build_schedule_list(self):
        outer = tk.Frame(self.root, bg=C['bg'])
        outer.pack(fill='both', expand=True, padx=20, pady=(0, 6))

        tk.Label(outer, text="Today's Schedule", font=('Segoe UI', 11, 'bold'),
                 fg=C['text'], bg=C['bg']).pack(anchor='w', pady=(0, 4))

        container = tk.Frame(outer, bg=C['bg'])
        container.pack(fill='both', expand=True)

        self.canvas = tk.Canvas(container, bg=C['bg'], highlightthickness=0)
        sb = ttk.Scrollbar(container, orient='vertical', command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=C['bg'])

        self.scroll_frame.bind(
            '<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=sb.set)

        sb.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)

        # Mouse-wheel scroll
        self.canvas.bind_all('<MouseWheel>',
            lambda e: self.canvas.yview_scroll(int(-1 * e.delta / 120), 'units'))

    def _build_controls(self):
        f = tk.Frame(self.root, bg=C['bg'])
        f.pack(fill='x', padx=20, pady=(0, 14))

        self.lbl_dot = tk.Label(f, text='●', font=('Segoe UI', 14),
                                fg=C['red'], bg=C['bg'])
        self.lbl_dot.pack(side='left', padx=(0, 6))

        self.lbl_status = tk.Label(f, text='Reminders OFF',
            font=('Segoe UI', 10), fg=C['muted'], bg=C['bg'])
        self.lbl_status.pack(side='left')

        self.btn_stop = tk.Button(f, text='Stop Reminders',
            command=self._stop_reminders,
            font=('Segoe UI', 10, 'bold'), bg=C['red'], fg='white',
            relief='flat', padx=16, pady=8, cursor='hand2',
            activebackground='#dc2626', activeforeground='white',
            bd=0, state='disabled')
        self.btn_stop.pack(side='right', padx=(4, 0))

        self.btn_start = tk.Button(f, text='Start Reminders',
            command=self._start_reminders,
            font=('Segoe UI', 10, 'bold'), bg=C['green'], fg='white',
            relief='flat', padx=16, pady=8, cursor='hand2',
            activebackground='#16a34a', activeforeground='white', bd=0)
        self.btn_start.pack(side='right', padx=4)

    # ── Schedule management ───────────────────────────────────────────────────

    def _switch_schedule(self, key):
        self.schedule_key = key
        self.notified.clear()
        if key == 'home_workout':
            self.btn_home.config(bg=C['accent'], fg='white')
            self.btn_gym.config(bg=C['card'], fg=C['muted'])
        else:
            self.btn_gym.config(bg=C['accent'], fg='white')
            self.btn_home.config(bg=C['card'], fg=C['muted'])
        self._load_and_render()

    def _load_and_render(self):
        self.activities = build_activities(self.schedule_key)
        self._render_list()

    def _render_list(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.activity_frames.clear()

        for act in self.activities:
            time_str = (act['start'].strftime('%I:%M %p').lstrip('0') +
                        ' – ' + act['end'].strftime('%I:%M %p').lstrip('0'))
            row = tk.Frame(self.scroll_frame, bg=C['card'], pady=8, padx=14)
            row.pack(fill='x', pady=2, padx=2)

            tk.Label(row, text=time_str, font=('Segoe UI', 9),
                     fg=C['muted'], bg=C['card'], width=22, anchor='w'
                     ).grid(row=0, column=0, sticky='w')
            tk.Label(row, text=act['title'], font=('Segoe UI', 11, 'bold'),
                     fg=C['text'], bg=C['card'], anchor='w'
                     ).grid(row=0, column=1, sticky='w', padx=(8, 0))

            self.activity_frames.append(row)

        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    # ── Periodic update (every second) ────────────────────────────────────────

    def _tick(self):
        now = datetime.now()

        # Info strip
        self.lbl_day.config(text=now.strftime('%A, %B %d %Y'))
        self.lbl_project.config(text=f'Project → {get_project_label()}')

        current_idx, next_idx = self._find_current_next(now)

        # Current activity
        if current_idx is not None:
            act = self.activities[current_idx]
            self.lbl_current.config(
                text=f"{act['title']}  ·  until {act['end'].strftime('%I:%M %p').lstrip('0')}",
                fg=C['text'])
        else:
            self.lbl_current.config(text='No active task right now', fg=C['muted'])

        # Countdown to next
        if next_idx is not None:
            act = self.activities[next_idx]
            secs_left = max(int((act['start'] - now).total_seconds()), 0)
            h, rem = divmod(secs_left, 3600)
            m, s = divmod(rem, 60)
            self.lbl_countdown.config(
                text=f'{h:02d}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}')
            self.lbl_next.config(
                text=f"Next: {act['title']} at {act['start'].strftime('%I:%M %p').lstrip('0')}")
        else:
            self.lbl_countdown.config(text='—')
            self.lbl_next.config(text='All activities complete for today!')

        # Highlight rows
        for i, frame in enumerate(self.activity_frames):
            if i == current_idx:
                self._colour_row(frame, C['active_bg'], C['accent_hi'], C['text'])
            elif current_idx is not None and i < current_idx:
                self._colour_row(frame, C['card_dim'], C['dim'], C['dim'])
            else:
                self._colour_row(frame, C['card'], C['muted'], C['text'])

        # Notifications
        if self.running:
            self._check_notifications(now)

        self.root.after(1000, self._tick)

    def _colour_row(self, frame, bg, time_fg, title_fg):
        frame.config(bg=bg)
        children = frame.winfo_children()
        if children:
            children[0].config(bg=bg, fg=time_fg)   # time label
        if len(children) > 1:
            children[1].config(bg=bg, fg=title_fg)  # title label

    def _find_current_next(self, now):
        current_idx = None
        next_idx = None
        for i, act in enumerate(self.activities):
            if act['start'] <= now < act['end']:
                current_idx = i
                if i + 1 < len(self.activities):
                    next_idx = i + 1
                break
        if current_idx is None:
            for i, act in enumerate(self.activities):
                if now < act['start']:
                    next_idx = i
                    break
        return current_idx, next_idx

    # ── Notifications ─────────────────────────────────────────────────────────

    def _check_notifications(self, now):
        for act in self.activities:
            key = act['start'].strftime('%H:%M') + '|' + act['title']
            if key not in self.notified:
                delta = (act['start'] - now).total_seconds()
                if -5 <= delta <= 5:
                    self.notified.add(key)
                    end_str = act['end'].strftime('%I:%M %p').lstrip('0')
                    threading.Thread(
                        target=self._notify,
                        args=(act['title'], f'Ends at {end_str}'),
                        daemon=True
                    ).start()

    @staticmethod
    def _notify(title, message):
        try:
            notification.notify(
                title=f'\u23f0 {title}',
                message=message,
                app_name='Daily Reminder',
                timeout=10,
            )
        except Exception as exc:
            print(f'[Notification error] {exc}')

    # ── Reminder toggle ───────────────────────────────────────────────────────

    def _start_reminders(self):
        self.running = True
        self.notified.clear()
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.lbl_dot.config(fg=C['green'])
        self.lbl_status.config(text='Reminders ON', fg=C['green'])

    def _stop_reminders(self):
        self.running = False
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        self.lbl_dot.config(fg=C['red'])
        self.lbl_status.config(text='Reminders OFF', fg=C['muted'])


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    root = tk.Tk()
    app = ReminderApp(root)
    root.mainloop()
