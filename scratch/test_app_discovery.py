import os
import winreg
from pathlib import Path

def get_registry_app_paths():
    apps = {}
    hives = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]
    sub_key = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
    
    for hive in hives:
        try:
            with winreg.OpenKey(hive, sub_key) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    try:
                        app_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, app_name) as app_key:
                            val, _ = winreg.QueryValueEx(app_key, "")
                            if val and os.path.exists(val):
                                clean_name = app_name.lower().replace(".exe", "")
                                apps[clean_name] = val
                    except Exception:
                        continue
        except Exception:
            continue
    return apps

def get_start_menu_shortcuts():
    shortcuts = {}
    paths = [
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    for p in paths:
        if p.exists():
            for lnk in p.rglob("*.lnk"):
                name = lnk.stem.lower()
                shortcuts[name] = str(lnk)
    return shortcuts

reg_apps = get_registry_app_paths()
lnk_apps = get_start_menu_shortcuts()

print(f"Discovered {len(reg_apps)} Registry App Paths:")
for k in sorted(reg_apps.keys())[:15]:
    print(f"  {k} -> {reg_apps[k]}")

print(f"\nDiscovered {len(lnk_apps)} Start Menu Shortcuts:")
for k in sorted(lnk_apps.keys())[:20]:
    print(f"  {k} -> {lnk_apps[k]}")
