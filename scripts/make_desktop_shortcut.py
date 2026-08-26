import os
import sys
import winreg

def get_desktop_path():
    # 1. 優先由 Windows 註冊表取得真實桌面路徑 (支援 OneDrive 重新導向與繁體中文「桌面」)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            val, _ = winreg.QueryValueEx(key, "Desktop")
            expanded = os.path.expandvars(val)
            if os.path.exists(expanded):
                return expanded
    except Exception:
        pass

    # 2. 備援方案：檢查 OneDrive 桌面
    user_profile = os.environ.get("USERPROFILE", "")
    onedrive = os.environ.get("OneDrive", "")
    candidates = [
        os.path.join(onedrive, "桌面"),
        os.path.join(onedrive, "Desktop"),
        os.path.join(user_profile, "OneDrive", "桌面"),
        os.path.join(user_profile, "OneDrive", "Desktop"),
        os.path.join(user_profile, "桌面"),
        os.path.join(user_profile, "Desktop"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
            
    return os.path.join(user_profile, "Desktop")

def create_shortcut():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_bat = os.path.join(base_dir, "start.bat")
    icon_ico = os.path.join(base_dir, "local_web", "static", "TL_logo.ico")
    icon_png = os.path.join(base_dir, "local_web", "static", "TL_logo.png")

    # 若尚未生成 .ico 檔，自動從 TL_logo.png 轉出多解析度 ICO
    if not os.path.exists(icon_ico) and os.path.exists(icon_png):
        try:
            from PIL import Image
            img = Image.open(icon_png).convert("RGBA")
            img.save(icon_ico, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        except Exception as e:
            print(f"轉檔 ICO 失敗: {e}")

    desktop_dir = get_desktop_path()
    shortcut_name = "裕珍皇 智慧冷鏈監控系統.lnk"
    shortcut_path = os.path.join(desktop_dir, shortcut_name)

    # 透過 VBS / WScript.Shell 建立標準 Windows .lnk 捷徑
    vbs_content = f'''Set ws = CreateObject("WScript.Shell")
Set sc = ws.CreateShortcut("{shortcut_path}")
sc.TargetPath = "{target_bat}"
sc.WorkingDirectory = "{base_dir}"
sc.Description = "裕珍皇 智慧冷鏈監控與能源管理系統 (一鍵開啟)"
'''
    if os.path.exists(icon_ico):
        vbs_content += f'sc.IconLocation = "{icon_ico},0"\n'
    vbs_content += 'sc.Save\n'

    temp_vbs = os.path.join(base_dir, "_temp_shortcut.vbs")
    with open(temp_vbs, "w", encoding="ansi", errors="ignore") as f:
        f.write(vbs_content)

    os.system(f'cscript //nologo "{temp_vbs}"')
    if os.path.exists(temp_vbs):
        try:
            os.remove(temp_vbs)
        except Exception:
            pass

    if os.path.exists(shortcut_path):
        print(f"SUCCESS: 捷徑建立成功 -> {shortcut_path}")
        return True
    else:
        print(f"FAILED: 捷徑建立失敗")
        return False

if __name__ == "__main__":
    create_shortcut()
