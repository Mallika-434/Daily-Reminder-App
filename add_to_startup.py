"""
Adds the reminder app to Windows startup via the registry.
Key: HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
Uses pythonw.exe so no console window appears on boot.
"""
import winreg
import sys
import os

APP_NAME = 'DailyReminderApp'
APP_DIR  = os.path.dirname(os.path.abspath(__file__))
APP_FILE = os.path.join(APP_DIR, 'app.py')

# Prefer pythonw.exe (no console window) but fall back to python.exe
pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
if not os.path.exists(pythonw):
    pythonw = sys.executable

# Build the command: cd to the app folder so schedule.json is found
CMD = f'"{pythonw}" "{APP_FILE}"'

REG_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'

try:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY,
                         0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, CMD)
    winreg.CloseKey(key)
    print(f'[OK] Added to startup as "{APP_NAME}"')
    print(f'     Command: {CMD}')
except Exception as e:
    print(f'[ERROR] Could not write to registry: {e}')
    sys.exit(1)
