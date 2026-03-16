"""
Removes the reminder app from the Windows startup registry.
Key: HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
"""
import winreg
import sys

APP_NAME = 'DailyReminderApp'
REG_KEY  = r'Software\Microsoft\Windows\CurrentVersion\Run'

try:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY,
                         0, winreg.KEY_SET_VALUE)
    winreg.DeleteValue(key, APP_NAME)
    winreg.CloseKey(key)
    print(f'[OK] Removed "{APP_NAME}" from startup.')
except FileNotFoundError:
    print(f'[INFO] "{APP_NAME}" was not found in startup — nothing to remove.')
except Exception as e:
    print(f'[ERROR] Could not modify registry: {e}')
    sys.exit(1)
