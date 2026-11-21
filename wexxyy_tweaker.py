"""
Wexxyy Tweaker - программа для оптимизации Windows 10/11.
Python 3.8+, только стандартная библиотека.

Запуск:  python wexxyy_tweaker.py   (сам запросит права администратора)
Сборка:  pip install pyinstaller
         pyinstaller --onefile --noconsole --uac-admin --name WexxyyTweaker wexxyy_tweaker.py
"""
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import winreg
from tkinter import colorchooser, messagebox, ttk
from tkinter import font as tkfont

_OLD_DIR = os.path.join(os.environ.get("APPDATA", "."), "WinTweaker")
APP_DIR = os.path.join(os.environ.get("APPDATA", "."), "WexxyyTweaker")
if os.path.isdir(_OLD_DIR) and not os.path.exists(APP_DIR):
    try:
        shutil.move(_OLD_DIR, APP_DIR)
    except OSError:
        pass
BACKUP_FILE = os.path.join(APP_DIR, "backup.json")
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

HIVES = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
DWORD, SZ = winreg.REG_DWORD, winreg.REG_SZ


# ---------- вспомогательные функции ----------
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, ""
    else:
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)


def run_ps(command):
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    return r.returncode, (r.stdout + r.stderr).strip()


def load_backup():
    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_backup(data):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
DEFAULT_SETTINGS = {"theme": "dark", "accent": "#35d07f", "brightness": 100,
                    "opacity": 100, "font_size": 9}
ACCENTS = [("Зелёный", "#35d07f"), ("Синий", "#3b8eea"), ("Красный", "#f0616d"),
           ("Фиолетовый", "#8b6cf0"), ("Оранжевый", "#f0a03c"), ("Бирюзовый", "#27c4cf"),
           ("Графит", "#8a93a3")]
PALETTES = {
    "light": {"bg": "#f2f3f5", "side": "#e7e9ec", "surface": "#ffffff", "surface2": "#eceef1",
              "fg": "#1b1d20", "muted": "#5d636b", "muted2": "#8a9099", "border": "#d8dbe0",
              "warn": "#b7791f", "danger": "#e5484d"},
    "dark": {"bg": "#121316", "side": "#0d0e10", "surface": "#1a1c20", "surface2": "#23262b",
             "fg": "#e8eaed", "muted": "#9aa0a8", "muted2": "#6f757d", "border": "#2b2e34",
             "warn": "#e8b04a", "danger": "#ee6670"},
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    for key, lo, hi in (("brightness", 40, 100), ("opacity", 60, 100), ("font_size", 8, 16)):
        try:
            s[key] = max(lo, min(hi, int(s[key])))
        except (TypeError, ValueError):
            s[key] = DEFAULT_SETTINGS[key]
    if s["theme"] not in ("light", "dark", "system"):
        s["theme"] = "system"
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(s["accent"])):
        s["accent"] = DEFAULT_SETTINGS["accent"]
    return s


def save_settings(s):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def scale_color(hexcolor, k):
    """Умножает яркость цвета на k (0..1)."""
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * k))) for c in (r, g, b))


def luminance(hexcolor):
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def system_uses_light():
    v = reg_read("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                 "AppsUseLightTheme")
    return True if v is None else bool(v[1])


def reg_read(hive, path, name):
    try:
        with winreg.OpenKey(HIVES[hive], path, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            val, typ = winreg.QueryValueEx(k, name)
            return [typ, val]
    except OSError:
        return None


def reg_write(hive, path, name, typ, value):
    with winreg.CreateKeyEx(HIVES[hive], path, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
        winreg.SetValueEx(k, name, 0, typ, value)


def reg_delete_value(hive, path, name):
    try:
        with winreg.OpenKey(HIVES[hive], path, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass


def reg_delete_tree(hive, path):
    """Удаляет ключ и все вложенные ключи."""
    try:
        with winreg.OpenKey(HIVES[hive], path, 0,
                            winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                reg_delete_tree(hive, path + "\\" + sub)
        winreg.DeleteKeyEx(HIVES[hive], path, winreg.KEY_WOW64_64KEY, 0)
    except OSError:
        pass


# ---------- описание твиков ----------
class RegTweak:
    """Твик из набора значений реестра. Прежние значения сохраняются для отката."""

    def __init__(self, tid, title, desc, items, note="", group="Реестр"):
        self.id, self.title, self.desc, self.note = tid, title, desc, note
        self.group = group
        self.items = items  # (hive, path, name, type, value)

    @property
    def info(self):
        h, p, n, _, v = self.items[0]
        s = f"{h}\\{p}  ->  {n} = {v}"
        if len(self.items) > 1:
            s += f"  (+ ещё {len(self.items) - 1})"
        return s

    def apply(self, backup):
        if self.id not in backup:  # сохраняем оригинал только один раз
            backup[self.id] = [
                {"hive": h, "path": p, "name": n, "old": reg_read(h, p, n)}
                for h, p, n, _, _ in self.items
            ]
        for h, p, n, t, v in self.items:
            reg_write(h, p, n, t, v)

    def revert(self, backup):
        for e in backup.get(self.id, []):
            if e["old"] is None:
                reg_delete_value(e["hive"], e["path"], e["name"])
            else:
                reg_write(e["hive"], e["path"], e["name"], e["old"][0], e["old"][1])
        backup.pop(self.id, None)


class ServiceTweak:
    def __init__(self, tid, title, desc, service):
        self.id, self.title, self.desc, self.note = tid, title, desc, ""
        self.service = service

    def apply(self, backup):
        code, out = run_ps(f"(Get-Service -Name '{self.service}' -ErrorAction Stop).StartType")
        if code != 0:
            raise RuntimeError(f"Служба {self.service} не найдена")
        if self.id not in backup:
            backup[self.id] = out.strip()
        run_ps(f"Stop-Service -Name '{self.service}' -Force -ErrorAction SilentlyContinue; "
               f"Set-Service -Name '{self.service}' -StartupType Disabled")

    def revert(self, backup):
        start = backup.get(self.id, "Automatic")
        run_ps(f"Set-Service -Name '{self.service}' -StartupType {start}; "
               f"if ('{start}' -eq 'Automatic') {{ Start-Service -Name '{self.service}' "
               f"-ErrorAction SilentlyContinue }}")
        backup.pop(self.id, None)


class ClassicMenuTweak:
    KEY = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"

    id = "classic_menu"
    title = "Классическое контекстное меню (Windows 11)"
    desc = "Возвращает старое меню правой кнопки без «Показать больше параметров»."
    note = "Нужен перезапуск проводника."

    def apply(self, backup):
        reg_write("HKCU", self.KEY + r"\InprocServer32", "", SZ, "")

    def revert(self, backup):
        reg_delete_tree("HKCU", self.KEY)


class HibernationTweak:
    id = "hibernate"
    title = "Отключить гибернацию"
    desc = "Удаляет hiberfil.sys и освобождает несколько ГБ на диске."
    note = "Пропадёт быстрый запуск."

    def apply(self, backup):
        subprocess.run(["powercfg", "-h", "off"], creationflags=NO_WINDOW, check=True)

    def revert(self, backup):
        subprocess.run(["powercfg", "-h", "on"], creationflags=NO_WINDOW, check=True)


class CleanTempTweak:
    """Одноразовое действие: откатить нельзя."""
    id = "clean_temp"
    title = "Очистить временные файлы"
    desc = "Удаляет содержимое папок TEMP пользователя и Windows."
    note = "Необратимо. Занятые файлы пропускаются."
    oneshot = True

    def apply(self, backup):
        paths = {tempfile.gettempdir(), os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Temp")}
        for base in paths:
            if not os.path.isdir(base):
                continue
            for name in os.listdir(base):
                full = os.path.join(base, name)
                try:
                    if os.path.isdir(full) and not os.path.islink(full):
                        shutil.rmtree(full, ignore_errors=True)
                    else:
                        os.remove(full)
                except OSError:
                    pass

    def revert(self, backup):
        raise RuntimeError("Это действие нельзя откатить")


class NagleTweak:
    """Отключение алгоритма Нейгла на всех сетевых интерфейсах."""
    group = "Интернет"
    id = "nagle"
    title = "Отключить алгоритм Нейгла (TcpAckFrequency, TCPNoDelay)"
    desc = "Снижает задержку (пинг) в играх и интерактивных приложениях."
    note = "На скорость скачивания почти не влияет. Нужна перезагрузка."
    info = r"HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\*  ->  TcpAckFrequency = 1, TCPNoDelay = 1"
    BASE = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
    NAMES = ("TcpAckFrequency", "TCPNoDelay")

    def _guids(self):
        out = []
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.BASE, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
        return out

    def apply(self, backup):
        guids = self._guids()
        if self.id not in backup:
            backup[self.id] = {
                g: {n: reg_read("HKLM", f"{self.BASE}\\{g}", n) for n in self.NAMES}
                for g in guids
            }
        for g in guids:
            for n in self.NAMES:
                reg_write("HKLM", f"{self.BASE}\\{g}", n, DWORD, 1)

    def revert(self, backup):
        for g, vals in backup.get(self.id, {}).items():
            path = f"{self.BASE}\\{g}"
            for n, old in vals.items():
                if old is None:
                    reg_delete_value("HKLM", path, n)
                else:
                    reg_write("HKLM", path, n, old[0], old[1])
        backup.pop(self.id, None)


class DnsTweak:
    """Смена DNS-серверов на активных физических адаптерах."""
    group = "Интернет"
    note = "Выберите только один DNS. Откат возвращает прежние настройки."
    LIST = (r"$l = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and -not $_.Virtual } | "
            r"ForEach-Object { [pscustomobject]@{ i = $_.ifIndex; ns = (Get-ItemProperty "
            r"('HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\' + $_.InterfaceGuid) "
            r"-Name NameServer -ErrorAction SilentlyContinue).NameServer } }); "
            r"ConvertTo-Json -InputObject $l -Compress")

    def __init__(self, tid, title, desc, servers):
        self.id, self.title, self.desc, self.servers = tid, title, desc, servers
        self.info = "Set-DnsClientServerAddress  ->  " + ", ".join(servers)

    def _adapters(self):
        code, out = run_ps(self.LIST)
        try:
            data = json.loads(out)
        except ValueError:
            raise RuntimeError("Не удалось получить список адаптеров")
        if isinstance(data, dict):
            data = [data]
        if not data:
            raise RuntimeError("Нет активных сетевых адаптеров")
        return data

    def apply(self, backup):
        data = self._adapters()
        if "dns_original" not in backup:
            backup["dns_original"] = data
        addrs = ",".join(f"'{s}'" for s in self.servers)
        cmd = "$ErrorActionPreference='Stop'; " + "; ".join(
            f"Set-DnsClientServerAddress -InterfaceIndex {int(d['i'])} -ServerAddresses {addrs}"
            for d in data) + "; Clear-DnsClientCache"
        code, out = run_ps(cmd)
        if code != 0:
            raise RuntimeError(out[:200])

    def revert(self, backup):
        data = backup.get("dns_original")
        if data is None:
            data = [{"i": d["i"], "ns": None} for d in self._adapters()]
        parts = []
        for d in data:
            idx = int(d["i"])
            old = [x for x in re.split(r"[,\s]+", d.get("ns") or "") if x]
            if old:
                addrs = ",".join(f"'{x}'" for x in old)
                parts.append(f"Set-DnsClientServerAddress -InterfaceIndex {idx} -ServerAddresses {addrs}")
            else:
                parts.append(f"Set-DnsClientServerAddress -InterfaceIndex {idx} -ResetServerAddresses")
        code, out = run_ps("$ErrorActionPreference='Stop'; " + "; ".join(parts) + "; Clear-DnsClientCache")
        if code != 0:
            raise RuntimeError(out[:200])
        backup.pop("dns_original", None)


class AutoTuningTweak:
    group = "Интернет"
    id = "autotune"
    title = "Автонастройка окна приёма TCP: Normal (AutoTuningLevelLocal)"
    desc = "Возвращает нормальную автонастройку TCP. Помогает, если её раньше отключали или ограничивали."
    note = "В Windows по умолчанию уже Normal, эффект только если значение меняли."
    info = "Set-NetTCPSetting -SettingName Internet -AutoTuningLevelLocal Normal"
    ALLOWED = ("Disabled", "HighlyRestricted", "Restricted", "Normal", "Experimental")

    def apply(self, backup):
        code, out = run_ps("(Get-NetTCPSetting -SettingName Internet).AutoTuningLevelLocal")
        if code != 0 or out.strip() not in self.ALLOWED:
            raise RuntimeError("Не удалось прочитать настройки TCP")
        if self.id not in backup:
            backup[self.id] = out.strip()
        code, out = run_ps("Set-NetTCPSetting -SettingName Internet -AutoTuningLevelLocal Normal")
        if code != 0:
            raise RuntimeError(out[:200])

    def revert(self, backup):
        old = backup.get(self.id, "Normal")
        if old not in self.ALLOWED:
            old = "Normal"
        run_ps(f"Set-NetTCPSetting -SettingName Internet -AutoTuningLevelLocal {old}")
        backup.pop(self.id, None)


class AdapterPowerTweak:
    group = "Интернет"
    id = "adapter_power"
    title = "Не отключать сетевой адаптер для экономии энергии"
    desc = "Убирает обрывы Wi-Fi и Ethernet после простоя (особенно на ноутбуках)."
    note = "Увеличивает расход батареи. Откат включает экономию обратно."
    info = "Set-NetAdapterPowerManagement  ->  AllowComputerToTurnOffDevice = Disabled"

    def _set(self, state):
        run_ps("Get-NetAdapter -Physical | ForEach-Object { Set-NetAdapterPowerManagement "
               f"-Name $_.Name -AllowComputerToTurnOffDevice {state} -ErrorAction SilentlyContinue }}")

    def apply(self, backup):
        self._set("Disabled")

    def revert(self, backup):
        self._set("Enabled")


class FlushDnsTweak:
    group = "Интернет"
    id = "flushdns"
    title = "Очистить кэш DNS"
    desc = "Помогает, когда сайт не открывается из-за устаревших DNS-записей."
    note = "Одноразовое действие, откат не нужен."
    info = "ipconfig /flushdns"

    def apply(self, backup):
        subprocess.run(["ipconfig", "/flushdns"], creationflags=NO_WINDOW, check=True)

    def revert(self, backup):
        raise RuntimeError("Это действие нельзя откатить")


ADV = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
CDM = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
DESK = r"Control Panel\Desktop"
MM = r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"
FS = r"SYSTEM\CurrentControlSet\Control\FileSystem"

TWEAKS = [
    RegTweak("telemetry", "Минимальная телеметрия (AllowTelemetry)",
             "Снижает уровень сбора диагностических данных.",
             [("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", DWORD, 0)],
             "На Home/Pro действует как минимальный уровень."),
    ServiceTweak("diagtrack", "Отключить службу DiagTrack",
                 "Служба «Функциональные возможности для подключённых пользователей и телеметрия».",
                 "DiagTrack"),
    RegTweak("adid", "Отключить рекламный идентификатор",
             "Приложения не смогут использовать ваш рекламный ID.",
             [("HKCU", r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", DWORD, 0)]),
    RegTweak("suggestions", "Убрать советы и рекомендуемые приложения",
             "Отключает рекламные предложения в «Пуске» и уведомлениях.",
             [("HKCU", CDM, n, DWORD, 0) for n in (
                 "SubscribedContent-338388Enabled", "SubscribedContent-338389Enabled",
                 "SubscribedContent-310093Enabled", "SilentInstalledAppsEnabled",
                 "SystemPaneSuggestionsEnabled", "SoftLandingEnabled")]),
    RegTweak("bing", "Отключить Bing в поиске «Пуска»",
             "Поиск ищет только локально.",
             [("HKCU", r"Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", DWORD, 1)]),
    RegTweak("fileext", "Показывать расширения файлов (HideFileExt)",
             "Видны .txt, .exe и т. д.",
             [("HKCU", ADV, "HideFileExt", DWORD, 0)]),
    RegTweak("hidden", "Показывать скрытые файлы (Hidden)",
             "Проводник показывает скрытые файлы и папки.",
             [("HKCU", ADV, "Hidden", DWORD, 1)]),
    RegTweak("menudelay", "Убрать задержку меню (MenuShowDelay)",
             "Меню открываются мгновенно.",
             [("HKCU", r"Control Panel\Desktop", "MenuShowDelay", SZ, "0")],
             "Применится после перезахода в систему."),
    RegTweak("gamedvr", "Отключить Game DVR",
             "Выключает фоновую запись игр Xbox Game Bar.",
             [("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", DWORD, 0),
              ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", DWORD, 0)]),
    RegTweak("prefetch", "Отключить Prefetch (EnablePrefetcher)",
             "Отключает предзагрузку данных запуска. Имеет смысл на SSD.",
             [("HKLM", MM + r"\PrefetchParameters", "EnablePrefetcher", DWORD, 0)],
             "Значения: 0 — выкл, 1 — приложения, 2 — загрузка, 3 — всё."),
    RegTweak("dump", "Малый дамп памяти при синем экране (CrashDumpEnabled)",
             "Вместо полного или автоматического дампа сохраняется малый (256 КБ).",
             [("HKLM", r"SYSTEM\CurrentControlSet\Control\CrashControl", "CrashDumpEnabled", DWORD, 3)],
             "Значения: 0 — нет, 1 — полный, 2 — ядра, 3 — малый, 7 — автоматический."),
    RegTweak("uac", "UAC: запрос без затемнения экрана (ConsentPromptBehaviorAdmin)",
             "Подтверждение UAC для администратора показывается без затемнения рабочего стола.",
             [("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "ConsentPromptBehaviorAdmin", DWORD, 4),
              ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "PromptOnSecureDesktop", DWORD, 0)],
             "Снижает защиту от подмены окна запроса."),
    RegTweak("wu", "Центр обновления: уведомлять перед загрузкой (AUOptions)",
             "Обновления не скачиваются и не ставятся без вашего подтверждения.",
             [("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU", "AUOptions", DWORD, 2),
              ("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU", "NoAutoUpdate", DWORD, 0)],
             "Не забывайте ставить обновления безопасности вручную."),
    RegTweak("hung", "Сократить ожидание зависшего приложения (HungAppTimeout)",
             "Предложение закрыть зависшую программу появляется через 3 с вместо 5 с.",
             [("HKCU", DESK, "HungAppTimeout", SZ, "3000")]),
    RegTweak("killsvc", "Быстрее завершать службы при выключении (WaitToKillServiceTimeout)",
             "Максимальное ожидание остановки служб: 2 с вместо 5 с.",
             [("HKLM", r"SYSTEM\CurrentControlSet\Control", "WaitToKillServiceTimeout", SZ, "2000")]),
    RegTweak("autoend", "Автозавершение зависших задач при выходе (AutoEndTasks)",
             "При выходе из системы зависшие программы закрываются без окна подтверждения.",
             [("HKCU", DESK, "AutoEndTasks", SZ, "1")],
             "Несохранённые данные в зависших программах будут потеряны."),
    RegTweak("clearpf", "Очищать файл подкачки при выключении (ClearPageFileAtShutdown)",
             "Повышает приватность: данные из pagefile.sys не остаются на диске.",
             [("HKLM", MM, "ClearPageFileAtShutdown", DWORD, 1)],
             "Выключение станет заметно дольше."),
    RegTweak("paging", "Не выгружать ядро и драйверы из ОЗУ (DisablePagingExecutive)",
             "Код ядра и драйверов остаётся в оперативной памяти.",
             [("HKLM", MM, "DisablePagingExecutive", DWORD, 1)],
             "Рекомендуется от 8 ГБ ОЗУ."),
    RegTweak("lastaccess", "Отключить метку последнего доступа NTFS (NtfsDisableLastAccessUpdate)",
             "Меньше записей на диск при чтении файлов.",
             [("HKLM", FS, "NtfsDisableLastAccessUpdate", DWORD, 1)],
             "Нужна перезагрузка."),
    RegTweak("8dot3", "Отключить короткие имена 8.3 (NtfsDisable8dot3NameCreation)",
             "Ускоряет работу с большими папками.",
             [("HKLM", FS, "NtfsDisable8dot3NameCreation", DWORD, 1)],
             "Старые установщики могут перестать работать. Нужна перезагрузка."),
    RegTweak("launchto", "Проводник открывается на «Этот компьютер» (LaunchTo)",
             "Вместо «Главная» / «Быстрый доступ».",
             [("HKCU", ADV, "LaunchTo", DWORD, 1)]),
    RegTweak("lowdisk", "Отключить уведомления о нехватке места (NoLowDiskSpaceChecks)",
             "Windows не будет предупреждать о заполненном системном диске.",
             [("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoLowDiskSpaceChecks", DWORD, 1)]),
    RegTweak("ttl", "TTL пакетов = 64 (DefaultTTL)",
             "Время жизни IP-пакетов по умолчанию (в Windows обычно 128).",
             [("HKLM", r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "DefaultTTL", DWORD, 64)],
             "На скорость почти не влияет. Нужна перезагрузка."),
    RegTweak("sysresp", "Приоритет активных программ (SystemResponsiveness = 10)",
             "Для фоновых задач резервируется 10% процессора вместо 20%.",
             [("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile", "SystemResponsiveness", DWORD, 10)]),
    RegTweak("nothrottle", "Отключить ограничение сети для мультимедиа (NetworkThrottlingIndex)",
             "Windows не притормаживает сетевые пакеты во время игр и воспроизведения видео.",
             [("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
               "NetworkThrottlingIndex", DWORD, 0xFFFFFFFF)],
             note="Эффект заметен в основном на быстрых каналах и в играх. Нужна перезагрузка.",
             group="Интернет"),
    RegTweak("doptim", "Отключить раздачу обновлений другим ПК (DODownloadMode)",
             "Windows не использует ваш канал для P2P-раздачи обновлений (Delivery Optimization).",
             [("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization", "DODownloadMode", DWORD, 0)],
             note="0 — загрузка только с серверов Microsoft.",
             group="Интернет"),
    RegTweak("ipv4pref", "Предпочитать IPv4 вместо IPv6 (DisabledComponents)",
             "Помогает, если сайты открываются с задержкой из-за неработающего IPv6 у провайдера.",
             [("HKLM", r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "DisabledComponents", DWORD, 0x20)],
             note="IPv6 не отключается полностью. Нужна перезагрузка.",
             group="Интернет"),
    NagleTweak(),
    AutoTuningTweak(),
    DnsTweak("dns_cf", "DNS Cloudflare 1.1.1.1 / 1.0.0.1",
             "Быстрый публичный DNS с упором на приватность.", ("1.1.1.1", "1.0.0.1")),
    DnsTweak("dns_google", "DNS Google 8.8.8.8 / 8.8.4.4",
             "Стабильный публичный DNS от Google.", ("8.8.8.8", "8.8.4.4")),
    AdapterPowerTweak(),
    FlushDnsTweak(),
    ServiceTweak("sysmain", "Отключить SysMain (Superfetch)",
                 "Полезно на SSD, на HDD может замедлить запуск программ.", "SysMain"),
    ClassicMenuTweak(),
    HibernationTweak(),
    CleanTempTweak(),
]


# ---------- интерфейс ----------
WRAP = 520
ICONS = {"Главная": "home", "Реестр": "list", "Интернет": "globe",
         "Система": "chip", "Интерфейс": "sliders"}
_TECH = re.compile(r"\s*\(\s*[A-Za-z0-9_]+(?:\s*(?:,|=)\s*[A-Za-z0-9_]+)*\s*\)")


def clean_title(t):
    """Убирает технические имена параметров в скобках из названия твика."""
    return _TECH.sub("", t).strip()


def draw_icon(cv, name, x, y, color):
    """Простые линейные иконки 16x16, нарисованные на Canvas."""
    kw = dict(fill=color, width=2, capstyle="round", joinstyle="round")
    if name == "home":
        cv.create_line(x + 1, y + 8, x + 8, y + 1, x + 15, y + 8, **kw)
        cv.create_line(x + 3, y + 7, x + 3, y + 15, x + 13, y + 15, x + 13, y + 7, **kw)
    elif name == "list":
        cv.create_line(x + 1, y + 3, x + 15, y + 3, **kw)
        cv.create_line(x + 1, y + 8, x + 15, y + 8, **kw)
        cv.create_line(x + 1, y + 13, x + 10, y + 13, **kw)
    elif name == "globe":
        cv.create_oval(x + 1, y + 1, x + 15, y + 15, outline=color, width=2)
        cv.create_oval(x + 5, y + 1, x + 11, y + 15, outline=color, width=1)
        cv.create_line(x + 1, y + 8, x + 15, y + 8, fill=color, width=1)
    elif name == "chip":
        cv.create_rectangle(x + 3, y + 3, x + 13, y + 13, outline=color, width=2)
        for d in (5, 11):
            cv.create_line(x + d, y, x + d, y + 3, fill=color, width=1)
            cv.create_line(x + d, y + 13, x + d, y + 16, fill=color, width=1)
            cv.create_line(x, y + d, x + 3, y + d, fill=color, width=1)
            cv.create_line(x + 13, y + d, x + 16, y + d, fill=color, width=1)
    elif name == "sliders":
        for ly, kx in ((3, 5), (8, 11), (13, 7)):
            cv.create_line(x + 1, y + ly, x + 15, y + ly, **kw)
            cv.create_oval(x + kx - 2, y + ly - 2, x + kx + 2, y + ly + 2, fill=color, outline=color)


class LogoMark(tk.Canvas):
    """Значок W в левом верхнем углу."""

    def __init__(self, master, app):
        super().__init__(master, width=40, height=40, highlightthickness=0, bd=0)
        self.app = app
        app.custom.append(self)
        self.redraw()

    def recolor(self):
        self.redraw()

    def redraw(self):
        c = self.app.colors
        self.delete("all")
        self.configure(bg=c["side"])
        self.create_polygon(rounded_poly(2, 2, 38, 38, 11), smooth=True, fill=c["accent"], outline="")
        self.create_text(20, 20, text="W", fill=c["on_accent"], font=self.app.fnt(5, True))


def rounded_poly(x1, y1, x2, y2, r):
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class RoundButton(tk.Canvas):
    """Скруглённая кнопка на Canvas. Роли: accent, danger, tile, nav, pill, seg."""

    def __init__(self, master, app, text, command=None, role="accent", bg="surface",
                 height=40, size=0, bold=True, anchor="center", autowidth=False, padx=16, icon=None):
        super().__init__(master, height=height, width=10, highlightthickness=0, bd=0)
        self.app, self.text, self.command, self.role, self.bgkey = app, text, command, role, bg
        self.size, self.bold, self.anchor = size, bold, anchor
        self.autowidth, self.padx, self.icon = autowidth, padx, icon
        self.hover = False
        self.selected = False
        if command:
            self.configure(cursor="hand2")
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)
        app.custom.append(self)
        self.redraw()

    def _enter(self, e):
        self.hover = True
        self.redraw()

    def _leave(self, e):
        self.hover = False
        self.redraw()

    def _click(self, e):
        if self.command:
            self.command()

    def set_text(self, text):
        self.text = text
        self.redraw()

    def recolor(self):
        self.redraw()

    def redraw(self):
        app = self.app
        c = app.colors
        font = app.fnt(self.size, self.bold)
        if self.autowidth:
            w = tkfont.Font(font=font).measure(self.text) + 2 * self.padx
            if int(float(self.cget("width"))) != w:
                self.configure(width=w)
        else:
            w = self.winfo_width()
        h = int(float(self.cget("height")))
        self.delete("all")
        self.configure(bg=c[self.bgkey])
        if w < 8:
            return
        role = self.role
        if role == "accent":
            fill, fg, line, hov = c["accent"], c["on_accent"], c["accent"], c["accent_hover"]
        elif role == "danger":
            fill, fg, line, hov = c["danger"], c["on_danger"], c["danger"], c["danger_hover"]
        elif role == "tile":
            fill, fg, line, hov = c["surface2"], c["accent"], c["surface2"], c["surface2"]
        elif role == "nav":
            fill = c["surface2"] if self.selected else c["side"]
            fg = c["fg"] if self.selected else c["muted"]
            line, hov = fill, c["surface2"]
        elif role == "pill":
            fill, fg, line, hov = c["bg"], c["accent"], c["accent"], c["bg"]
        else:  # seg
            fill = c["accent"] if self.selected else c["surface2"]
            fg = c["on_accent"] if self.selected else c["fg"]
            line = fill
            hov = c["accent_hover"] if self.selected else c["border"]
        if self.hover and self.command:
            if role == "tile":
                line = c["accent"]
            else:
                fill = line = hov
        self.create_polygon(rounded_poly(1, 1, w - 1, h - 1, 10), smooth=True,
                            fill=fill, outline=line, width=1)
        tx = 16
        if self.icon:
            draw_icon(self, self.icon, 16, h / 2 - 8, c["accent"] if self.selected else c["muted"])
            tx = 46
        if role == "nav" and self.selected:
            self.create_rectangle(0, h * 0.22, 3, h * 0.78, fill=c["accent"], outline="")
        if self.anchor == "w":
            self.create_text(tx, h / 2, text=self.text, fill=fg, font=font, anchor="w",
                             width=max(10, w - tx - 8))
        else:
            self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=font,
                             justify="center", width=max(10, w - 20))


class ToggleSwitch(tk.Canvas):
    def __init__(self, master, app, var, bg="surface"):
        super().__init__(master, width=40, height=22, highlightthickness=0, bd=0, cursor="hand2")
        self.app, self.var, self.bgkey = app, var, bg
        self.bind("<Button-1>", lambda e: self.var.set(not self.var.get()))
        var.trace_add("write", lambda *a: self.redraw())
        app.custom.append(self)
        self.redraw()

    def recolor(self):
        self.redraw()

    def redraw(self):
        c = self.app.colors
        on = self.var.get()
        self.delete("all")
        self.configure(bg=c[self.bgkey])
        self.create_polygon(rounded_poly(1, 1, 39, 21, 10), smooth=True,
                            fill=c["accent"] if on else c["surface2"],
                            outline=c["accent"] if on else c["border"])
        x = 29 if on else 11
        self.create_oval(x - 7, 4, x + 7, 18, fill=c["on_accent"] if on else c["muted"], outline="")


class Slider(tk.Canvas):
    def __init__(self, master, app, lo, hi, value, command, bg="surface"):
        super().__init__(master, height=26, width=10, highlightthickness=0, bd=0, cursor="hand2")
        self.app, self.lo, self.hi, self.value = app, lo, hi, value
        self.command, self.bgkey = command, bg
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        app.custom.append(self)

    def _drag(self, e):
        w = self.winfo_width()
        t = min(1.0, max(0.0, (e.x - 12) / max(1, w - 24)))
        v = int(round(self.lo + t * (self.hi - self.lo)))
        if v != self.value:
            self.value = v
            self.redraw()
            self.command(v)

    def set(self, v):
        self.value = v
        self.redraw()

    def recolor(self):
        self.redraw()

    def redraw(self):
        c = self.app.colors
        self.delete("all")
        self.configure(bg=c[self.bgkey])
        w = self.winfo_width()
        if w < 30:
            return
        x = 12 + (self.value - self.lo) / (self.hi - self.lo) * (w - 24)
        self.create_line(12, 13, w - 12, 13, width=4, fill=c["border"], capstyle="round")
        self.create_line(12, 13, x, 13, width=4, fill=c["accent"], capstyle="round")
        self.create_oval(x - 8, 5, x + 8, 21, fill=c["accent"], outline=c[self.bgkey], width=2)


class Swatch(tk.Canvas):
    def __init__(self, master, app, color, bg="surface"):
        super().__init__(master, width=30, height=30, highlightthickness=0, bd=0, cursor="hand2")
        self.app, self.color, self.bgkey = app, color, bg
        self.bind("<Button-1>", lambda e: app.set_accent(color))
        app.custom.append(self)
        self.redraw()

    def recolor(self):
        self.redraw()

    def redraw(self):
        c = self.app.colors
        self.delete("all")
        self.configure(bg=c[self.bgkey])
        if self.app.settings["accent"].lower() == self.color.lower():
            self.create_oval(1, 1, 29, 29, outline=c["fg"], width=2)
        self.create_oval(5, 5, 25, 25, fill=self.color, outline="")


class Card(tk.Canvas):
    """Скруглённая карточка. Содержимое кладётся в card.body."""

    def __init__(self, master, app, bg="bg", fill="surface", pad=16, radius=14):
        super().__init__(master, highlightthickness=0, bd=0, height=40, width=10)
        self.app, self.bgkey, self.fillkey = app, bg, fill
        self.pad, self.radius = pad, radius
        self.body = tk.Frame(self, bd=0, highlightthickness=0)
        app.reg(self.body, bg=fill)
        self.win = self.create_window(pad, pad, window=self.body, anchor="nw")
        self.bind("<Configure>", self._on_canvas)
        self.body.bind("<Configure>", self._on_body)
        app.custom.append(self)

    def _on_canvas(self, e):
        self.itemconfigure(self.win, width=max(1, e.width - 2 * self.pad))
        self.redraw()

    def _on_body(self, e):
        h = self.body.winfo_reqheight() + 2 * self.pad
        if int(float(self.cget("height"))) != h:
            self.configure(height=h)

    def recolor(self):
        self.redraw()

    def redraw(self):
        c = self.app.colors
        self.delete("card")
        self.configure(bg=c[self.bgkey])
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8 or h < 8:
            return
        self.create_polygon(rounded_poly(1, 1, w - 1, h - 1, self.radius), smooth=True,
                            fill=c[self.fillkey], outline=c["border"], tags="card")
        self.tag_lower("card")


class App(tk.Tk):
    GROUPS = ("Реестр", "Интернет", "Система")

    def __init__(self):
        super().__init__()
        self.title("Wexxyy Tweaker")
        self.geometry("1040x700")
        self.minsize(900, 600)
        self.backup = load_backup()
        self.settings = load_settings()
        self.vars, self.pages, self.scrolls, self.nav, self.sliders = {}, {}, {}, {}, {}
        self.registry, self.custom = [], []
        self.theme_btns = {}
        self.current = None
        self.compute_colors()
        self.configure(bg=self.colors["bg"])

        self.build_layout()
        self.build_home()
        for g in self.GROUPS:
            self.build_tweak_page(g)
        self.build_interface_page()

        self.apply_theme()
        self.show_page("Главная")
        self.update_stats()
        self.bind_all("<MouseWheel>", self.on_wheel)
        self.say(f"Резервные данные: {BACKUP_FILE}")

    # ----- цвета, шрифты, оформление -----
    def compute_colors(self):
        st = self.settings
        mode = st["theme"]
        if mode == "system":
            mode = "light" if system_uses_light() else "dark"
        self.mode = mode
        k = st["brightness"] / 100
        c = {n: scale_color(v, k) for n, v in PALETTES[mode].items()}
        acc = st["accent"]
        c["accent"] = scale_color(acc, k)
        c["accent_hover"] = scale_color(acc, k * 0.85)
        c["on_accent"] = scale_color("#000000" if luminance(acc) > 0.55 else "#ffffff", k)
        c["danger_hover"] = scale_color(PALETTES[mode]["danger"], k * 0.85)
        c["on_danger"] = scale_color("#ffffff", k)
        self.colors = c

    def fnt(self, delta=0, bold=False, mono=False):
        size = max(7, self.settings["font_size"] + delta)
        return ("Consolas" if mono else "Segoe UI", size, "bold" if bold else "normal")

    def paint(self, w, opts):
        kw = {}
        for opt, v in opts.items():
            kw[opt] = self.fnt(*v[1:]) if isinstance(v, tuple) else self.colors[v]
        w.configure(**kw)

    def reg(self, w, **opts):
        self.registry.append((w, opts))
        self.paint(w, opts)
        return w

    def mk_frame(self, parent, bg="surface"):
        return self.reg(tk.Frame(parent, bd=0, highlightthickness=0), bg=bg)

    def mk_label(self, parent, text, bg="surface", fg="fg", delta=0, bold=False,
                 mono=False, wrap=0):
        lb = tk.Label(parent, text=text, anchor="w", justify="left", bd=0,
                      highlightthickness=0, wraplength=wrap)
        return self.reg(lb, bg=bg, fg=fg, font=("f", delta, bold, mono))

    def apply_theme(self):
        self.compute_colors()
        c = self.colors
        alive = []
        for w, opts in self.registry:
            try:
                self.paint(w, opts)
                alive.append((w, opts))
            except tk.TclError:
                pass
        self.registry = alive
        for val, b in self.theme_btns.items():
            b.selected = (val == self.settings["theme"])
        for w in self.custom:
            try:
                w.recolor()
            except tk.TclError:
                pass
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar", background=c["surface2"], troughcolor=c["bg"],
                        bordercolor=c["bg"], arrowcolor=c["bg"], lightcolor=c["surface2"],
                        darkcolor=c["surface2"], gripcount=0)
        style.map("Vertical.TScrollbar", background=[("active", c["border"])])
        self.configure(bg=c["bg"])
        try:
            self.attributes("-alpha", self.settings["opacity"] / 100)
        except tk.TclError:
            pass
        self.set_dark_titlebar(self.mode == "dark")

    def set_dark_titlebar(self, dark):
        """Тёмный заголовок окна (Windows 10 2004+ и Windows 11)."""
        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1 if dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
        except Exception:
            pass

    # ----- каркас: боковая панель, заголовок, панель действий -----
    def build_layout(self):
        self.side = tk.Frame(self, width=240, bd=0, highlightthickness=0)
        self.reg(self.side, bg="side")
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)
        self.main = self.mk_frame(self, "bg")
        self.main.pack(side="left", fill="both", expand=True)

        logo = self.mk_frame(self.side, "side")
        logo.pack(fill="x", padx=18, pady=(22, 22))
        LogoMark(logo, self).pack(side="left", padx=(0, 10))
        names = self.mk_frame(logo, "side")
        names.pack(side="left")
        self.mk_label(names, "WEXXYY", bg="side", bold=True, delta=3).pack(anchor="w")
        self.mk_label(names, "TWEAKER", bg="side", fg="accent", bold=True, delta=-1).pack(anchor="w")

        self.add_nav("Главная")
        self.mk_label(self.side, "КАТЕГОРИИ", bg="side", fg="muted2", delta=-1,
                      bold=True).pack(anchor="w", padx=22, pady=(18, 6))
        for g in self.GROUPS + ("Интерфейс",):
            self.add_nav(g)
        self.mk_label(self.side, "Wexxyy Tweaker 1.0", bg="side", fg="muted2",
                      delta=-1).pack(side="bottom", anchor="w", padx=22, pady=16)

        head = self.mk_frame(self.main, "bg")
        head.pack(fill="x", padx=28, pady=(24, 14))
        self.title_lbl = self.mk_label(head, "", bg="bg", bold=True, delta=7)
        self.title_lbl.pack(side="left")
        self.pill = RoundButton(head, self, "●  ПРАВА АДМИНИСТРАТОРА", None, role="pill", bg="bg",
                                height=30, size=-1, autowidth=True)
        self.pill.pack(side="right")

        self.actionbar = self.mk_frame(self.main, "bg")
        RoundButton(self.actionbar, self, "ПРИМЕНИТЬ ВЫБРАННОЕ", self.apply_selected,
                    role="accent", bg="bg", height=40, autowidth=True, padx=22).pack(side="left")
        RoundButton(self.actionbar, self, "ОТКАТИТЬ ВЫБРАННОЕ", self.revert_selected,
                    role="danger", bg="bg", height=40, autowidth=True,
                    padx=22).pack(side="left", padx=10)
        self.status = self.mk_label(self.actionbar, "", bg="bg", fg="muted", delta=-1)
        self.status.pack(side="left", padx=8)

        self.content = self.mk_frame(self.main, "bg")
        self.content.pack(fill="both", expand=True, padx=28)

    def add_nav(self, name):
        b = RoundButton(self.side, self, name.upper(), lambda n=name: self.show_page(n),
                        role="nav", bg="side", height=44, anchor="w",
                        icon=ICONS.get(name))
        b.pack(fill="x", padx=14, pady=2)
        self.nav[name] = b

    def show_page(self, name):
        if self.current:
            self.pages[self.current].pack_forget()
        self.current = name
        self.pages[name].pack(fill="both", expand=True)
        for n, b in self.nav.items():
            b.selected = (n == name)
            b.redraw()
        self.title_lbl.configure(text=name.upper())
        if name in self.GROUPS:
            self.actionbar.pack(side="bottom", fill="x", before=self.content,
                                padx=28, pady=(8, 20))
        else:
            self.actionbar.pack_forget()

    def scroll_area(self, parent):
        wrap = self.mk_frame(parent, "bg")
        cv = tk.Canvas(wrap, highlightthickness=0, bd=0)
        self.reg(cv, bg="bg")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=cv.yview)
        inner = self.mk_frame(cv, "bg")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        win = cv.create_window(0, 0, window=inner, anchor="nw")
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True, padx=(0, 6))
        return wrap, inner, cv

    def on_wheel(self, event):
        cv = self.scrolls.get(self.current)
        if cv:
            cv.yview_scroll(int(-event.delta / 120), "units")

    # ----- страницы -----
    def build_home(self):
        page = self.mk_frame(self.content, "bg")
        self.pages["Главная"] = page

        stats = self.mk_frame(page, "bg")
        stats.pack(fill="x", pady=(0, 12))
        self.stat = {}
        for i, (key, caption) in enumerate((("total", "ДОСТУПНО ТВИКОВ"), ("applied", "ПРИМЕНЕНО"),
                                            ("selected", "ВЫБРАНО"))):
            stats.columnconfigure(i, weight=1, uniform="stats")
            sc = Card(stats, self, pad=16)
            sc.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0 if i == 2 else 6))
            self.stat[key] = self.mk_label(sc.body, "0", fg="accent", delta=14, bold=True)
            self.stat[key].pack(anchor="w")
            self.mk_label(sc.body, caption, fg="muted2", delta=-1, bold=True).pack(anchor="w")

        card = Card(page, self, pad=18)
        card.pack(fill="x", pady=(0, 14))
        b = card.body
        row = self.mk_frame(b)
        row.pack(fill="x")
        RoundButton(row, self, "ПРИМЕНИТЬ ВЫБРАННОЕ", self.apply_selected, role="accent",
                    height=46).pack(side="left", fill="x", expand=True, padx=(0, 6))
        RoundButton(row, self, "ОТКАТИТЬ ВЫБРАННОЕ", self.revert_selected, role="danger",
                    height=46).pack(side="left", fill="x", expand=True, padx=(6, 0))
        tiles = self.mk_frame(b)
        tiles.pack(fill="x", pady=(12, 0))
        items = (("ТОЧКА ВОССТАНОВЛЕНИЯ", self.make_restore_point),
                 ("ПЕРЕЗАПУСК ПРОВОДНИКА", self.restart_explorer),
                 ("СНЯТЬ ВЫБОР", self.clear_selection),
                 ("ПАПКА РЕЗЕРВНЫХ КОПИЙ", self.open_backup_dir))
        for i, (text, cmd) in enumerate(items):
            tiles.columnconfigure(i, weight=1, uniform="tiles")
            RoundButton(tiles, self, text, cmd, role="tile", height=50,
                        size=-1).grid(row=0, column=i, sticky="ew", padx=4)

        logcard = Card(page, self, pad=18)
        logcard.pack(fill="x")
        lb = logcard.body
        head = self.mk_frame(lb)
        head.pack(fill="x", pady=(0, 10))
        self.mk_label(head, "ЖУРНАЛ", fg="muted2", delta=-1, bold=True).pack(side="left")
        self.mk_label(head, "●  ГОТОВ", fg="accent", delta=-1, bold=True).pack(side="right")
        self.log = tk.Text(lb, height=12, bd=0, highlightthickness=0, wrap="word",
                           state="disabled", padx=12, pady=10)
        self.reg(self.log, bg="surface2", fg="fg", insertbackground="fg",
                 selectbackground="accent", font=("f", -1, False, True))
        self.log.pack(fill="x")

    def build_tweak_page(self, group):
        wrap, inner, cv = self.scroll_area(self.content)
        self.pages[group] = wrap
        self.scrolls[group] = cv
        for t in TWEAKS:
            if getattr(t, "group", "Система") != group:
                continue
            var = tk.BooleanVar()
            self.vars[t.id] = var
            var.trace_add("write", lambda *a: self.update_stats())
            card = Card(inner, self, pad=14, radius=12)
            card.pack(fill="x", pady=4, padx=(0, 4))
            body = card.body
            ToggleSwitch(body, self, var).pack(side="left", anchor="n", padx=(0, 14), pady=2)
            txt = self.mk_frame(body)
            txt.pack(side="left", fill="x", expand=True)
            self.mk_label(txt, clean_title(t.title), bold=True, wrap=WRAP).pack(anchor="w")
            self.mk_label(txt, t.desc, fg="muted", delta=-1, wrap=WRAP).pack(anchor="w", pady=(2, 0))
            note = getattr(t, "note", "")
            if note and not note.startswith("Значения"):
                self.mk_label(txt, "⚠ " + note, fg="warn", delta=-1, wrap=WRAP).pack(anchor="w", pady=(2, 0))

    def build_interface_page(self):
        wrap, inner, cv = self.scroll_area(self.content)
        self.pages["Интерфейс"] = wrap
        self.scrolls["Интерфейс"] = cv

        def section(title):
            card = Card(inner, self, pad=18)
            card.pack(fill="x", pady=(0, 14), padx=(0, 4))
            self.mk_label(card.body, title, fg="muted2", delta=-1,
                          bold=True).pack(anchor="w", pady=(0, 10))
            return card.body

        b = section("ТЕМА")
        row = self.mk_frame(b)
        row.pack(fill="x")
        for i, (val, text) in enumerate((("light", "СВЕТЛАЯ"), ("dark", "ТЁМНАЯ"),
                                         ("system", "КАК В СИСТЕМЕ"))):
            row.columnconfigure(i, weight=1, uniform="seg")
            btn = RoundButton(row, self, text, lambda v=val: self.set_theme(v), role="seg",
                              height=38, size=-1)
            btn.selected = (val == self.settings["theme"])
            btn.grid(row=0, column=i, sticky="ew", padx=4)
            self.theme_btns[val] = btn

        b = section("АКЦЕНТНЫЙ ЦВЕТ")
        row = self.mk_frame(b)
        row.pack(fill="x")
        for _, col in ACCENTS:
            Swatch(row, self, col).pack(side="left", padx=3)
        RoundButton(row, self, "СВОЙ ЦВЕТ…", self.pick_accent, role="tile", height=34, size=-1,
                    autowidth=True).pack(side="left", padx=(14, 0))

        b = section("ОФОРМЛЕНИЕ")
        self.add_slider(b, "Яркость интерфейса", "brightness", 40, 100, "%")
        self.add_slider(b, "Прозрачность окна", "opacity", 60, 100, "%")
        self.add_slider(b, "Размер шрифта", "font_size", 8, 16, " pt")
        RoundButton(b, self, "СБРОСИТЬ ОФОРМЛЕНИЕ", self.reset_theme, role="tile", height=38,
                    size=-1, autowidth=True).pack(anchor="w", pady=(16, 0))

    def add_slider(self, parent, title, key, lo, hi, unit):
        head = self.mk_frame(parent)
        head.pack(fill="x", pady=(10, 2))
        self.mk_label(head, title, bold=True).pack(side="left")
        val = self.mk_label(head, f"{self.settings[key]}{unit}", fg="muted")
        val.pack(side="right")

        def on_change(v):
            self.settings[key] = v
            val.configure(text=f"{v}{unit}")
            self.apply_theme()
            save_settings(self.settings)

        sl = Slider(parent, self, lo, hi, self.settings[key], on_change)
        sl.pack(fill="x")
        self.sliders[key] = (sl, val, unit)

    # ----- настройки оформления -----
    def set_theme(self, val):
        self.settings["theme"] = val
        self.apply_theme()
        save_settings(self.settings)

    def set_accent(self, color):
        self.settings["accent"] = color
        self.apply_theme()
        save_settings(self.settings)

    def pick_accent(self):
        _, color = colorchooser.askcolor(color=self.settings["accent"], title="Акцентный цвет")
        if color:
            self.set_accent(color)

    def reset_theme(self):
        self.settings.update(DEFAULT_SETTINGS)
        for key, (sl, lbl, unit) in self.sliders.items():
            sl.set(self.settings[key])
            lbl.configure(text=f"{self.settings[key]}{unit}")
        self.apply_theme()
        save_settings(self.settings)

    # ----- действия -----
    def say(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.status.configure(text=msg)
        self.update_idletasks()

    def update_stats(self):
        applied = len([k for k in self.backup if k != "dns_original"])
        self.stat["total"].configure(text=str(len(TWEAKS)))
        self.stat["applied"].configure(text=str(applied))
        self.stat["selected"].configure(text=str(len(self.selected())))

    def selected(self):
        return [t for t in TWEAKS if self.vars[t.id].get()]

    def run_tweaks(self, action):
        items = self.selected()
        if not items:
            messagebox.showinfo("Wexxyy Tweaker", "Ничего не выбрано.")
            return
        for t in items:
            try:
                getattr(t, action)(self.backup)
                save_backup(self.backup)
                self.say(f"OK: {t.title}")
            except Exception as e:
                self.say(f"ОШИБКА: {t.title}: {e}")
        self.update_stats()
        self.say("Часть твиков вступит в силу после перезагрузки или перезахода в систему.")

    def apply_selected(self):
        if messagebox.askyesno("Подтверждение",
                               "Применить выбранные твики?\nРекомендуется сначала создать точку восстановления."):
            self.run_tweaks("apply")

    def revert_selected(self):
        self.run_tweaks("revert")

    def clear_selection(self):
        for v in self.vars.values():
            v.set(False)
        self.say("Выбор снят.")

    def open_backup_dir(self):
        os.makedirs(APP_DIR, exist_ok=True)
        try:
            os.startfile(APP_DIR)
        except OSError as e:
            self.say(f"Не удалось открыть папку: {e}")

    def make_restore_point(self):
        self.say("Создаю точку восстановления...")
        code, out = run_ps('Checkpoint-Computer -Description "Wexxyy Tweaker" '
                           '-RestorePointType MODIFY_SETTINGS')
        self.say("Точка восстановления создана." if code == 0
                 else f"Не удалось (защита системы выключена или лимит 1 раз в 24 ч): {out[:200]}")

    def restart_explorer(self):
        subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], creationflags=NO_WINDOW)
        subprocess.Popen(["explorer.exe"])
        self.say("Проводник перезапущен.")


if __name__ == "__main__":
    if os.name != "nt":
        sys.exit("Программа работает только в Windows.")
    if not is_admin():
        relaunch_as_admin()
        sys.exit()
    App().mainloop()
