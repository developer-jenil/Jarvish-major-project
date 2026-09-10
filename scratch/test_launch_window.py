import sys
sys.path.insert(0, ".")
import os
import subprocess
import ctypes
from jarvis.skills.browser_control import get_chrome_path, get_active_chrome_profile

chrome = get_chrome_path()
profile = get_active_chrome_profile()
url = "https://mail.google.com/mail/u/0/?view=cm&fs=1&to=mom@example.com&su=Testing+Auto+Popup&body=Hello+Mom+from+JARVIS"

print(f"Chrome: {chrome}")
print(f"Profile: {profile}")

params = f'--profile-directory="{profile}" --new-window "{url}"'
print(f"Params: {params}")

# Allow set foreground window
ctypes.windll.user32.AllowSetForegroundWindow(-1)
ret = ctypes.windll.shell32.ShellExecuteW(None, "open", chrome, params, None, 1)
print(f"ShellExecuteW return code: {ret}")
