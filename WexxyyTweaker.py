# -*- coding: utf-8 -*-
"""
Wexxyy Tweaker — оптимизация Windows 10/11.
Запуск:  python WexxyyTweaker.py   (сам запросит права администратора)
Сборка:  build.bat  ->  WexxyyTweaker.exe с иконкой W
"""
import sys, os, json, ctypes, subprocess, threading, queue, struct, zlib, base64
from dataclasses import dataclass, field

try:
    import winreg
except ImportError:          # не Windows (нужно только для --make-icon)
    winreg = None

APP = "Wexxyy Tweaker"
DATA_DIR = os.path.join(os.environ.get("APPDATA", "."), "WexxyyTweaker")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
ICO_FILE = os.path.join(DATA_DIR, "W.ico")
NO_WINDOW = 0x08000000

# ───────────────────────── иконка W (без внешних библиотек) ─────────────────────────
def _render_icon(n):
    ss = 3
    pts = [(.20, .27), (.345, .73), (.50, .40), (.655, .73), (.80, .27)]
    segs = list(zip(pts[:-1], pts[1:]))
    hw, rad = 0.058, 0.22
    c1, c2 = (150, 112, 255), (70, 52, 225)

    def dist(px, py, a, b):
        ax, ay = a; bx, by = b
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        qx, qy = ax + t * dx, ay + t * dy
        return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5

    rows = []
    for y in range(n):
        row = bytearray()
        for x in range(n):
            R = G = B = cnt = 0
            for sy in range(ss):
                for sx in range(ss):
                    u = (x + (sx + .5) / ss) / n
                    v = (y + (sy + .5) / ss) / n
                    ddx = max(abs(u - .5) - (.5 - rad), 0)
                    ddy = max(abs(v - .5) - (.5 - rad), 0)
                    if ddx * ddx + ddy * ddy > rad * rad:
                        continue
                    cnt += 1
                    if any(dist(u, v, a, b) <= hw for a, b in segs):
                        R += 255; G += 255; B += 255
                    else:
                        k = (u + v) / 2
                        R += c1[0] + (c2[0] - c1[0]) * k
                        G += c1[1] + (c2[1] - c1[1]) * k
                        B += c1[2] + (c2[2] - c1[2]) * k
            if cnt:
                row += bytes((int(R / cnt), int(G / cnt), int(B / cnt), int(255 * cnt / (ss * ss))))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))
    return rows


def _png(n, rows):
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def write_ico(path):
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [_png(s, _render_icon(s)) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(imgs))
    off = 6 + 16 * len(imgs)
    entries = b""
    for s, d in zip(sizes, imgs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(d), off)
        off += len(d)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(head + entries + b"".join(imgs))


def ensure_icon():
    if os.path.exists(ICO_FILE):
        return ICO_FILE
    os.makedirs(DATA_DIR, exist_ok=True)
    bundled = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "W.ico")
    try:
        if os.path.exists(bundled):
            with open(bundled, "rb") as s, open(ICO_FILE, "wb") as d:
                d.write(s.read())
        else:
            write_ico(ICO_FILE)
    except Exception:
        write_ico(ICO_FILE)
    return ICO_FILE


# ───────────────────────── ярлык на рабочем столе ─────────────────────────
def create_desktop_shortcut():
    ico = ensure_icon()
    if getattr(sys, "frozen", False):
        target, args = sys.executable, ""
        wd = os.path.dirname(sys.executable)
    else:
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        target = pyw if os.path.exists(pyw) else sys.executable
        args = '"%s"' % os.path.abspath(__file__)
        wd = os.path.dirname(os.path.abspath(__file__))
    q = lambda s: s.replace("'", "''")
    script = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\\Wexxyy Tweaker.lnk');"
        f"$s.TargetPath='{q(target)}';$s.Arguments='{q(args)}';$s.WorkingDirectory='{q(wd)}';"
        f"$s.IconLocation='{q(ico)},0';$s.Description='Wexxyy Tweaker';$s.Save()"
    )
    code, out = run(script, ps=True)
    # обновить кэш иконок, чтобы W появилась сразу
    run("ie4uinit.exe -show")
    return code == 0


# ───────────────────────── запуск команд / реестр ─────────────────────────
def run(cmd, ps=False):
    try:
        if ps:
            enc = base64.b64encode(cmd.encode("utf-16-le")).decode()
            args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc]
            r = subprocess.run(args, capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW)
        else:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def _hive(n):
    return winreg.HKEY_LOCAL_MACHINE if n == "HKLM" else winreg.HKEY_CURRENT_USER


def _rtype(n):
    return {"DWORD": winreg.REG_DWORD, "SZ": winreg.REG_SZ, "BINARY": winreg.REG_BINARY}[n]


def reg_read(hive, path, name):
    try:
        with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            v, t = winreg.QueryValueEx(k, name)
            return True, t, v
    except OSError:
        return False, None, None


def reg_write(hive, path, name, rtype, value):
    if rtype == "BINARY" and isinstance(value, str):
        value = bytes.fromhex(value)
    with winreg.CreateKeyEx(_hive(hive), path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
        winreg.SetValueEx(k, name, 0, _rtype(rtype), value)


def reg_delete(hive, path, name):
    try:
        with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass


def reg_matches(a):
    _, hive, path, name, rtype, val, _d = a
    ex, t, cur = reg_read(hive, path, name)
    if not ex:
        return False
    if rtype == "DWORD":
        return int(cur) & 0xFFFFFFFF == int(val) & 0xFFFFFFFF
    if rtype == "BINARY":
        return bytes(cur) == bytes.fromhex(val)
    return str(cur) == str(val)


# ───────────────────────── описание твиков ─────────────────────────
@dataclass
class Tweak:
    id: str
    section: str
    name: str
    desc: str
    actions: list = field(default_factory=list)
    risky: bool = False
    oneshot: bool = False


TWEAKS = []


def T(sec, id, name, desc, *actions, risky=False, oneshot=False):
    TWEAKS.append(Tweak(id, sec, name, desc, list(actions), risky, oneshot))


def reg(hive, path, name, value, rtype="DWORD", default=None):
    return ("reg", hive, path, name, rtype, value, default)


def sh(apply, revert=None):
    return ("sh", apply, revert)


def ps(apply, revert=None):
    return ("ps", apply, revert)


def svc(name, default="demand"):
    return ("sh", f"sc config {name} start= disabled & sc stop {name}", f"sc config {name} start= {default}")


def pc(sub, setting, on, off):
    base = "powercfg -setacvalueindex SCHEME_CURRENT %s %s %s & powercfg -setactive SCHEME_CURRENT"
    return sh(base % (sub, setting, on), base % (sub, setting, off))


def bcd(key, val):
    return sh(f"bcdedit /set {key} {val}", f"bcdedit /deletevalue {key}")


def task(path, enable_default=True):
    return sh(f'schtasks /Change /TN "{path}" /Disable', f'schtasks /Change /TN "{path}" /Enable')


EXP = r"Software\Microsoft\Windows\CurrentVersion\Explorer"
ADV = EXP + r"\Advanced"
CDM = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
SYSP = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
GAMES = SYSP + r"\Tasks\Games"
MM = r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"
TCP = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
POL = r"SOFTWARE\Policies\Microsoft\Windows"
DC = POL + r"\DataCollection"
GCS = r"System\GameConfigStore"
GFX = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
DSK = r"Control Panel\Desktop"
PERS = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

# ── Процессор ──
S = "Процессор"
T(S, "cpu_throttle", "Отключить Power Throttling", "Windows не душит фоновые процессы и игры ради экономии энергии.", reg("HKLM", r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling", "PowerThrottlingOff", 1))
T(S, "cpu_prio", "Приоритет активного окна (0x26)", "Больше процессорного времени для программы, с которой вы работаете.", reg("HKLM", r"SYSTEM\CurrentControlSet\Control\PriorityControl", "Win32PrioritySeparation", 38, default=2))
T(S, "cpu_sysresp", "SystemResponsiveness = 0", "Отдаёт максимум CPU приоритетным мультимедиа-задачам и играм.", reg("HKLM", SYSP, "SystemResponsiveness", 0, default=20))
T(S, "cpu_nthrottle", "Отключить NetworkThrottlingIndex", "Убирает ограничение сетевых пакетов при мультимедиа-нагрузке.", reg("HKLM", SYSP, "NetworkThrottlingIndex", 4294967295, default=10))
T(S, "cpu_gpuprio", "GPU Priority для игр = 8", "Повышает приоритет графики для задач категории Games.", reg("HKLM", GAMES, "GPU Priority", 8))
T(S, "cpu_gameprio", "CPU Priority для игр = 6", "Повышает приоритет процессора для задач категории Games.", reg("HKLM", GAMES, "Priority", 6, default=2))
T(S, "cpu_gamesched", "Scheduling Category = High", "Планировщик считает игры высокоприоритетными.", reg("HKLM", GAMES, "Scheduling Category", "High", "SZ", default="Medium"))
T(S, "cpu_gamesfio", "SFIO Priority = High", "Высокий приоритет дисковых операций игр.", reg("HKLM", GAMES, "SFIO Priority", "High", "SZ", default="Normal"))
T(S, "cpu_minstate", "Минимальное состояние CPU 100%", "Процессор не снижает частоту в простое (больше нагрев и расход).", pc("SUB_PROCESSOR", "PROCTHROTTLEMIN", 100, 5))
T(S, "cpu_boost", "Агрессивный Turbo Boost", "Режим повышения частоты — агрессивный.", pc("SUB_PROCESSOR", "PERFBOOSTMODE", 2, 1))
T(S, "cpu_parking", "Отключить парковку ядер", "Все ядра всегда активны — меньше задержек в играх.", pc("SUB_PROCESSOR", "CPMINCORES", 100, 10))
T(S, "cpu_idle", "Запретить простой ядер (Idle Disable)", "Максимальная отзывчивость, но сильный нагрев и расход энергии.", pc("SUB_PROCESSOR", "IDLEDISABLE", 1, 0), risky=True)
T(S, "cpu_dyntick", "Отключить Dynamic Tick", "Стабильнее таймер, меньше микрофризов. Нужна перезагрузка.", bcd("disabledynamictick", "yes"))
T(S, "cpu_platclock", "Отключить Platform Clock (HPET)", "Принудительно не использовать HPET как таймер. Нужна перезагрузка.", bcd("useplatformclock", "false"))
T(S, "cpu_tsc", "TSC Sync Policy = Enhanced", "Улучшенная синхронизация таймера ядер. Нужна перезагрузка.", bcd("tscsyncpolicy", "enhanced"))
T(S, "cpu_timerres", "Глобальное разрешение таймера", "Разрешает программам запрашивать точный таймер (Windows 11).", reg("HKLM", r"SYSTEM\CurrentControlSet\Control\Session Manager\kernel", "GlobalTimerResolutionRequests", 1))
T(S, "cpu_fth", "Отключить Fault Tolerant Heap", "Windows не включает защитные «костыли» для вылетающих программ.", reg("HKLM", r"SOFTWARE\Microsoft\FTH", "Enabled", 0, default=1))
T(S, "cpu_spectre", "Отключить защиту Spectre/Meltdown", "Прирост на старых CPU, но снижает безопасность. Нужна перезагрузка.", reg("HKLM", MM, "FeatureSettingsOverride", 3), reg("HKLM", MM, "FeatureSettingsOverrideMask", 3), risky=True)
T(S, "cpu_vbs", "Отключить целостность памяти (VBS/HVCI)", "Заметный прирост FPS на некоторых системах, но ниже защита. Перезагрузка.", reg("HKLM", r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity", "Enabled", 0), risky=True)

# ── Оперативная память ──
S = "Оперативная память"
T(S, "ram_pagingexec", "Ядро и драйверы держать в ОЗУ", "DisablePagingExecutive — не выгружать код ядра в файл подкачки.", reg("HKLM", MM, "DisablePagingExecutive", 1, default=0))
T(S, "ram_prefetch", "Отключить Prefetcher", "Не нужен на SSD, экономит ОЗУ и записи.", reg("HKLM", MM + r"\PrefetchParameters", "EnablePrefetcher", 0, default=3))
T(S, "ram_superfetch", "Отключить Superfetch (реестр)", "Прекращает предзагрузку программ в память.", reg("HKLM", MM + r"\PrefetchParameters", "EnableSuperfetch", 0, default=3))
T(S, "ram_memcomp", "Отключить сжатие памяти", "Меньше нагрузка на CPU, если ОЗУ достаточно (от 16 ГБ).", ps("Disable-MMAgent -MemoryCompression", "Enable-MMAgent -MemoryCompression"))
T(S, "ram_pagecomb", "Отключить Page Combining", "Не объединять одинаковые страницы памяти.", ps("Disable-MMAgent -PageCombining", "Enable-MMAgent -PageCombining"))
T(S, "ram_clearpf", "Очищать файл подкачки при выключении", "Безопаснее, но выключение дольше.", reg("HKLM", MM, "ClearPageFileAtShutdown", 1, default=0))
T(S, "ram_dump", "Отключить дампы памяти при сбое", "Не создавать огромные файлы дампов.", reg("HKLM", r"SYSTEM\CurrentControlSet\Control\CrashControl", "CrashDumpEnabled", 0, default=7))
T(S, "ram_autoreboot", "Не перезагружаться при BSOD", "Синий экран остаётся на экране — можно прочитать код ошибки.", reg("HKLM", r"SYSTEM\CurrentControlSet\Control\CrashControl", "AutoReboot", 0, default=1))
T(S, "ram_wer", "Отключить отчёты об ошибках", "Windows не собирает и не отправляет отчёты о сбоях.", reg("HKLM", r"SOFTWARE\Microsoft\Windows\Windows Error Reporting", "Disabled", 1, default=0))
T(S, "ram_timeouts", "Быстрое закрытие программ", "Сокращает ожидание зависших приложений до 1–2 секунд.", reg("HKCU", DSK, "WaitToKillAppTimeout", "2000", "SZ", "5000"), reg("HKCU", DSK, "HungAppTimeout", "1000", "SZ", "5000"), reg("HKCU", DSK, "AutoEndTasks", "1", "SZ", "0"), reg("HKCU", DSK, "LowLevelHooksTimeout", 1000))
T(S, "ram_svctimeout", "Быстрая остановка служб", "WaitToKillServiceTimeout = 2 сек — быстрее выключение.", reg("HKLM", r"SYSTEM\CurrentControlSet\Control", "WaitToKillServiceTimeout", "2000", "SZ", "5000"))
T(S, "ram_bgapps", "Запретить фоновые приложения", "Приложения Microsoft Store не работают в фоне.", reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled", 1), reg("HKLM", POL + r"\AppPrivacy", "LetAppsRunInBackground", 2))
T(S, "ram_hibernate", "Отключить гибернацию", "Удаляет hiberfil.sys — освобождает место, равное объёму ОЗУ.", sh("powercfg -h off", "powercfg -h on"))
T(S, "ram_faststart", "Отключить быстрый запуск", "Чистая загрузка системы при каждом включении, меньше багов.", reg("HKLM", r"SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled", 0, default=1))

# ── Диск и SSD ──
S = "Диск и SSD"
T(S, "disk_lastaccess", "Не писать время последнего доступа", "Меньше записей на диск при чтении файлов.", sh("fsutil behavior set disablelastaccess 1", "fsutil behavior set disablelastaccess 2"))
T(S, "disk_8dot3", "Отключить короткие имена 8.3", "Ускоряет работу с папками с большим числом файлов.", sh("fsutil behavior set disable8dot3 1", "fsutil behavior set disable8dot3 2"))
T(S, "disk_memusage", "Больше кэша пула NTFS", "fsutil memoryusage 2 — больше памяти под метаданные NTFS.", sh("fsutil behavior set memoryusage 2", "fsutil behavior set memoryusage 1"))
T(S, "disk_defrag", "Отключить плановую дефрагментацию", "SSD не нуждается в дефрагментации (TRIM продолжит работать).", task(r"\Microsoft\Windows\Defrag\ScheduledDefrag"))
T(S, "disk_trim", "Включить TRIM", "Гарантирует работу TRIM для SSD.", sh("fsutil behavior set disabledeletenotify 0", "fsutil behavior set disabledeletenotify 0"))
T(S, "disk_reserved", "Отключить зарезервированное хранилище", "Освобождает ~7 ГБ, которые Windows резервирует под обновления.", sh("DISM /Online /Set-ReservedStorageState /State:Disabled", "DISM /Online /Set-ReservedStorageState /State:Enabled"))
T(S, "disk_storagesense", "Отключить Контроль памяти", "Windows не удаляет файлы автоматически.", reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy", "01", 0, default=1))
T(S, "disk_thumbs", "Отключить кэш миниатюр", "Не создавать файлы Thumbs.db / кэш превью.", reg("HKCU", r"Software\Policies\Microsoft\Windows\Explorer", "DisableThumbnailCache", 1), reg("HKCU", r"Software\Policies\Microsoft\Windows\Explorer", "DisableThumbsDBOnNetworkFolders", 1))
T(S, "disk_maint", "Отключить автообслуживание Windows", "Windows не запускает обслуживание в простое ПК.", reg("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\Maintenance", "MaintenanceDisabled", 1, default=0))
T(S, "disk_do", "Отключить раздачу обновлений другим ПК", "Delivery Optimization больше не использует ваш диск и канал.", reg("HKLM", POL + r"\DeliveryOptimization", "DODownloadMode", 0))
T(S, "disk_lowspace", "Не показывать «мало места на диске»", "Убирает уведомления о нехватке места.", reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoLowDiskSpaceChecks", 1))

# ── Сеть и пинг ──
S = "Сеть и пинг"
T(S, "net_nagle", "Отключить алгоритм Нейгла", "TcpAckFrequency=1 и TCPNoDelay=1 — ниже пинг в играх.",
  ps(r"Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces' | ForEach-Object { Set-ItemProperty -Path $_.PSPath -Name TcpAckFrequency -Value 1 -Type DWord; Set-ItemProperty -Path $_.PSPath -Name TCPNoDelay -Value 1 -Type DWord }",
     r"Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces' | ForEach-Object { Remove-ItemProperty -Path $_.PSPath -Name TcpAckFrequency,TCPNoDelay -ErrorAction SilentlyContinue }"))
T(S, "net_ecn", "Включить ECN", "Явное уведомление о перегрузке сети.", sh("netsh int tcp set global ecncapability=enabled", "netsh int tcp set global ecncapability=disabled"))
T(S, "net_rsc", "Отключить RSC", "Receive Segment Coalescing увеличивает задержку — выключаем.", sh("netsh int tcp set global rsc=disabled", "netsh int tcp set global rsc=enabled"))
T(S, "net_rto", "Начальный RTO = 2000 мс", "Быстрее повторная отправка потерянных пакетов.", sh("netsh int tcp set global initialRto=2000", "netsh int tcp set global initialRto=3000"))
T(S, "net_heur", "Отключить эвристику TCP", "Windows не меняет параметры автонастройки сама.", sh("netsh int tcp set heuristics disabled", "netsh int tcp set heuristics enabled"))
T(S, "net_dca", "Включить DCA", "Direct Cache Access — быстрее обработка пакетов (если поддерживает сетевая карта).", sh("netsh int tcp set global dca=enabled", "netsh int tcp set global dca=disabled"))
T(S, "net_ports", "Больше портов и быстрый TIME_WAIT", "MaxUserPort=65534, TcpTimedWaitDelay=30.", reg("HKLM", TCP, "MaxUserPort", 65534, default=None), reg("HKLM", TCP, "TcpTimedWaitDelay", 30))
T(S, "net_ttl", "DefaultTTL = 64", "Стандартное значение TTL для большинства сетей.", reg("HKLM", TCP, "DefaultTTL", 64))
T(S, "net_icmp", "Отключить ICMP-редиректы", "Защита от подмены маршрутов.", reg("HKLM", TCP, "EnableICMPRedirect", 0, default=1))
T(S, "net_ipv6", "Отключить IPv6", "Если провайдер не использует IPv6 — меньше сетевой «возни». Нужна перезагрузка.", reg("HKLM", r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "DisabledComponents", 255, default=0), risky=True)
T(S, "net_teredo", "Отключить Teredo", "Туннель IPv6 поверх IPv4 — обычно не нужен.", sh("netsh interface teredo set state disabled", "netsh interface teredo set state default"))
T(S, "net_6to4", "Отключить 6to4", "Устаревший туннельный протокол.", sh("netsh interface 6to4 set state disabled", "netsh interface 6to4 set state default"))
T(S, "net_isatap", "Отключить ISATAP", "Устаревший туннельный протокол.", sh("netsh interface isatap set state disabled", "netsh interface isatap set state default"))
T(S, "net_dnscache", "Увеличить кэш DNS", "MaxCacheTtl=86400, MaxNegativeCacheTtl=0.", reg("HKLM", r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters", "MaxCacheTtl", 86400), reg("HKLM", r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters", "MaxNegativeCacheTtl", 0, default=900))
T(S, "net_llmnr", "Отключить LLMNR", "Меньше лишнего широковещательного трафика, выше безопасность.", reg("HKLM", POL.replace("Windows", "Windows NT") + r"\DNSClient", "EnableMulticast", 0))
T(S, "net_netbios", "Отключить NetBIOS поверх TCP/IP", "Устаревший протокол, не нужен дома.",
  ps("Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object IPEnabled | Invoke-CimMethod -MethodName SetTcpipNetbios -Arguments @{TcpipNetbiosOptions=2}",
     "Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object IPEnabled | Invoke-CimMethod -MethodName SetTcpipNetbios -Arguments @{TcpipNetbiosOptions=0}"))
T(S, "net_qos", "Снять резерв канала QoS", "Windows не резервирует часть интернета под служебные нужды.", reg("HKLM", POL + r"\Psched", "NonBestEffortLimit", 0))
T(S, "net_nicpower", "Отключить энергосбережение адаптеров", "Сетевые карты не «засыпают» — стабильнее пинг.",
  ps("Get-NetAdapter | ForEach-Object { Disable-NetAdapterPowerManagement -Name $_.Name -ErrorAction SilentlyContinue }",
     "Get-NetAdapter | ForEach-Object { Enable-NetAdapterPowerManagement -Name $_.Name -ErrorAction SilentlyContinue }"))
T(S, "net_lso", "Отключить Large Send Offload", "Меньше задержка в играх на некоторых сетевых картах.",
  ps("Get-NetAdapter | ForEach-Object { Disable-NetAdapterLso -Name $_.Name -ErrorAction SilentlyContinue }",
     "Get-NetAdapter | ForEach-Object { Enable-NetAdapterLso -Name $_.Name -ErrorAction SilentlyContinue }"))
T(S, "net_smb1", "Отключить SMBv1", "Старый уязвимый протокол — отключить безопасно.",
  ps("Disable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -NoRestart", "Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -NoRestart"))
T(S, "net_ncsi", "Отключить проверку интернета NCSI", "Windows не обращается к серверам Microsoft для проверки связи.", reg("HKLM", POL + r"\NetworkConnectivityStatusIndicator", "NoActiveProbe", 1))
T(S, "net_dns_cf", "DNS Cloudflare 1.1.1.1", "Быстрый и приватный DNS для активных адаптеров.",
  ps("Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses ('1.1.1.1','1.0.0.1') }",
     "Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses }"))
T(S, "net_dns_g", "DNS Google 8.8.8.8", "Альтернатива Cloudflare (не включайте оба сразу).",
  ps("Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses ('8.8.8.8','8.8.4.4') }",
     "Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses }"))
T(S, "net_irp", "Увеличить IRPStackSize", "Больше стек запросов для сетевых операций.", reg("HKLM", r"SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters", "IRPStackSize", 32))

# ── Графика и игры ──
S = "Графика и игры"
T(S, "gfx_dvr", "Отключить Xbox Game DVR", "Выключает фоновую запись игр — больше FPS.", reg("HKCU", GCS, "GameDVR_Enabled", 0, default=1), reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0, default=1), reg("HKLM", POL + r"\GameDVR", "AllowGameDVR", 0))
T(S, "gfx_fso", "Отключить оптимизацию полного экрана", "Классический эксклюзивный полноэкранный режим в играх.", reg("HKCU", GCS, "GameDVR_FSEBehaviorMode", 2), reg("HKCU", GCS, "GameDVR_HonorUserFSEBehaviorMode", 1), reg("HKCU", GCS, "GameDVR_FSEBehavior", 2), reg("HKCU", GCS, "GameDVR_DXGIHonorFSEWindowsCompatible", 1))
T(S, "gfx_gamemode", "Включить игровой режим", "Windows приостанавливает фоновые задачи во время игры.", reg("HKCU", r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1), reg("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1))
T(S, "gfx_gamebar", "Отключить подсказки Game Bar", "Убирает всплывающие панели Xbox Game Bar.", reg("HKCU", r"Software\Microsoft\GameBar", "UseNexusForGameBarEnabled", 0, default=1), reg("HKCU", r"Software\Microsoft\GameBar", "ShowStartupPanel", 0, default=1))
T(S, "gfx_hags", "Аппаратное планирование GPU (HAGS)", "Включает HAGS на поддерживаемых видеокартах. Нужна перезагрузка.", reg("HKLM", GFX, "HwSchMode", 2, default=1))
T(S, "gfx_windowed", "Оптимизация игр в окне", "Улучшает FPS и VRR в оконном режиме DirectX 10/11.", reg("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", "DirectXUserGlobalSettings", "SwapEffectUpgradeEnable=1;VRROptimizeEnable=1;", "SZ"))
T(S, "gfx_mpo", "Отключить Multiplane Overlay", "Лечит мерцание и чёрные экраны на некоторых видеокартах.", reg("HKLM", r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode", 5))
T(S, "gfx_tdr", "Увеличить TdrDelay", "Видеодрайвер получает 10 сек на ответ — меньше сбросов драйвера.", reg("HKLM", GFX, "TdrDelay", 10), reg("HKLM", GFX, "TdrDdiDelay", 10))
T(S, "gfx_transp", "Отключить прозрачность", "Меньше нагрузка на GPU в интерфейсе.", reg("HKCU", PERS, "EnableTransparency", 0, default=1))
T(S, "gfx_anim", "Отключить анимации окон", "Окна сворачиваются и открываются мгновенно.", reg("HKCU", r"Control Panel\Desktop\WindowMetrics", "MinAnimate", "0", "SZ", "1"), reg("HKCU", EXP + r"\VisualEffects", "VisualFXSetting", 2, default=0))
T(S, "gfx_mask", "Режим «Наилучшее быстродействие»", "UserPreferencesMask: отключает тени, плавность и прочие эффекты.", reg("HKCU", DSK, "UserPreferencesMask", "9012038010000000", "BINARY"))
T(S, "gfx_mouse", "Отключить ускорение мыши", "Точность указателя — 1:1, лучше для шутеров.", reg("HKCU", r"Control Panel\Mouse", "MouseSpeed", "0", "SZ", "1"), reg("HKCU", r"Control Panel\Mouse", "MouseThreshold1", "0", "SZ", "6"), reg("HKCU", r"Control Panel\Mouse", "MouseThreshold2", "0", "SZ", "10"))
T(S, "gfx_kbd", "Быстрый отклик клавиатуры", "Минимальная задержка и максимальная скорость повтора.", reg("HKCU", r"Control Panel\Keyboard", "KeyboardDelay", "0", "SZ", "1"), reg("HKCU", r"Control Panel\Keyboard", "KeyboardSpeed", "31", "SZ", "31"))
T(S, "gfx_sticky", "Отключить залипание клавиш", "Не мешает Shift×5 в играх.", reg("HKCU", r"Control Panel\Accessibility\StickyKeys", "Flags", "506", "SZ", "510"), reg("HKCU", r"Control Panel\Accessibility\Keyboard Response", "Flags", "122", "SZ", "126"), reg("HKCU", r"Control Panel\Accessibility\ToggleKeys", "Flags", "58", "SZ", "62"))

# ── Приватность ──
S = "Приватность"
T(S, "prv_telemetry", "Минимум телеметрии", "AllowTelemetry = 0 (только безопасность).", reg("HKLM", DC, "AllowTelemetry", 0), reg("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection", "AllowTelemetry", 0))
T(S, "prv_feedback", "Отключить запросы отзывов", "Windows не спрашивает ваше мнение.", reg("HKLM", DC, "DoNotShowFeedbackNotifications", 1))
T(S, "prv_adid", "Отключить рекламный ID", "Приложения не получают ваш рекламный идентификатор.", reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0, default=1), reg("HKLM", POL + r"\AdvertisingInfo", "DisabledByGroupPolicy", 1))
T(S, "prv_tailored", "Отключить персонализированные советы", "Microsoft не использует диагностику для подбора рекламы.", reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0, default=1))
T(S, "prv_cortana", "Отключить Cortana", "Выключает голосового помощника.", reg("HKLM", POL + r"\Windows Search", "AllowCortana", 0))
T(S, "prv_bing", "Отключить Bing в поиске Пуск", "Поиск ищет только на ПК.", reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0, default=1), reg("HKCU", r"Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", 1))
T(S, "prv_websearch", "Отключить веб-поиск Windows", "Запросы не уходят в интернет.", reg("HKLM", POL + r"\Windows Search", "ConnectedSearchUseWeb", 0), reg("HKLM", POL + r"\Windows Search", "DisableWebSearch", 1))
T(S, "prv_activity", "Отключить журнал действий", "Timeline / история действий не собирается.", reg("HKLM", POL + r"\System", "EnableActivityFeed", 0), reg("HKLM", POL + r"\System", "PublishUserActivities", 0), reg("HKLM", POL + r"\System", "UploadUserActivities", 0))
T(S, "prv_location", "Отключить геолокацию", "Система не определяет ваше местоположение.", reg("HKLM", POL + r"\LocationAndSensors", "DisableLocation", 1))
T(S, "prv_cdm_start", "Убрать рекомендации в Пуске", "Нет предложенных приложений и рекламы в меню.", reg("HKCU", CDM, "SubscribedContent-338388Enabled", 0, default=1), reg("HKCU", CDM, "SystemPaneSuggestionsEnabled", 0, default=1))
T(S, "prv_cdm_lock", "Убрать рекламу на экране блокировки", "Отключает Spotlight-подсказки и ротацию.", reg("HKCU", CDM, "RotatingLockScreenEnabled", 0, default=1), reg("HKCU", CDM, "RotatingLockScreenOverlayEnabled", 0, default=1), reg("HKCU", CDM, "SubscribedContent-338387Enabled", 0, default=1))
T(S, "prv_cdm_auto", "Запретить автоустановку приложений", "Отключает «рекомендуемые» игры и приложения Microsoft.", reg("HKCU", CDM, "SilentInstalledAppsEnabled", 0, default=1), reg("HKCU", CDM, "PreInstalledAppsEnabled", 0, default=1), reg("HKCU", CDM, "OemPreInstalledAppsEnabled", 0, default=1), reg("HKCU", CDM, "ContentDeliveryAllowed", 0, default=1))
T(S, "prv_cdm_tips", "Отключить подсказки и советы", "Нет уведомлений «Как получить максимум от Windows».", reg("HKCU", CDM, "SubscribedContent-338389Enabled", 0, default=1), reg("HKCU", CDM, "SoftLandingEnabled", 0, default=1))
T(S, "prv_trackprogs", "Не отслеживать запуск программ", "Пуск не запоминает часто используемые приложения.", reg("HKCU", ADV, "Start_TrackProgs", 0, default=1))
T(S, "prv_ceip", "Отключить программу улучшения (CEIP)", "Не отправлять данные об использовании.", reg("HKLM", r"SOFTWARE\Policies\Microsoft\SQMClient\Windows", "CEIPEnable", 0))
T(S, "prv_appcompat", "Отключить телеметрию совместимости", "Выключает инвентаризацию приложений и PCA.", reg("HKLM", POL + r"\AppCompat", "AITEnable", 0), reg("HKLM", POL + r"\AppCompat", "DisableInventory", 1), reg("HKLM", POL + r"\AppCompat", "DisablePCA", 1))
T(S, "prv_ink", "Отключить сбор рукописного и текстового ввода", "Не собирать образцы набора текста.", reg("HKCU", r"Software\Microsoft\InputPersonalization", "RestrictImplicitInkCollection", 1, default=0), reg("HKCU", r"Software\Microsoft\InputPersonalization", "RestrictImplicitTextCollection", 1, default=0))
T(S, "prv_speech", "Отключить онлайн-распознавание речи", "Голос не отправляется в облако.", reg("HKCU", r"Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy", "HasAccepted", 0, default=1))
T(S, "prv_tasks", "Отключить задачи телеметрии", "Выключает плановые задания Compatibility Appraiser, CEIP и т.п.",
  task(r"\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser"),
  task(r"\Microsoft\Windows\Application Experience\ProgramDataUpdater"),
  task(r"\Microsoft\Windows\Customer Experience Improvement Program\Consolidator"),
  task(r"\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip"))
T(S, "prv_remote", "Отключить удалённого помощника", "Закрывает вход через Remote Assistance.", reg("HKLM", r"SYSTEM\CurrentControlSet\Control\Remote Assistance", "fAllowToGetHelp", 0, default=1))
T(S, "prv_copilot", "Отключить Copilot", "Убирает Windows Copilot.", reg("HKCU", r"Software\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot", 1))
T(S, "prv_recall", "Отключить Recall / анализ ИИ", "Запрещает локальную запись и анализ экрана.", reg("HKCU", r"Software\Policies\Microsoft\Windows\WindowsAI", "DisableAIDataAnalysis", 1))
T(S, "prv_onedrive", "Отключить OneDrive", "Синхронизация файлов не запускается.", reg("HKLM", POL + r"\OneDrive", "DisableFileSyncNGSC", 1))
T(S, "prv_edge", "Отключить фоновую работу Edge", "Edge не стартует заранее и не живёт в фоне.", reg("HKLM", r"SOFTWARE\Policies\Microsoft\Edge", "StartupBoostEnabled", 0), reg("HKLM", r"SOFTWARE\Policies\Microsoft\Edge", "BackgroundModeEnabled", 0))
T(S, "prv_clip", "Отключить историю буфера обмена", "Win+V не сохраняет и не синхронизирует буфер.", reg("HKCU", r"Software\Microsoft\Clipboard", "EnableClipboardHistory", 0, default=1), reg("HKLM", POL + r"\System", "AllowCrossDeviceClipboard", 0))
T(S, "prv_insider", "Отключить программу Insider", "Блокирует предварительные сборки.", reg("HKLM", DC, "AllowBuildPreview", 0))
T(S, "prv_feeds", "Отключить «Новости и интересы»", "Нет ленты новостей на панели задач.", reg("HKLM", POL + r"\Windows Feeds", "EnableFeeds", 0))
T(S, "prv_sync", "Отключить синхронизацию настроек", "Настройки не отправляются в облако Microsoft.", reg("HKLM", POL + r"\SettingSync", "DisableSettingSync", 2), reg("HKLM", POL + r"\SettingSync", "DisableSettingSyncUserOverride", 1))

# ── Интерфейс ──
S = "Интерфейс"
T(S, "ui_ext", "Показывать расширения файлов", "Видно .exe, .txt, .png и т.д.", reg("HKCU", ADV, "HideFileExt", 0, default=1))
T(S, "ui_hidden", "Показывать скрытые файлы", "Скрытые папки и файлы видны в Проводнике.", reg("HKCU", ADV, "Hidden", 1, default=2))
T(S, "ui_super", "Показывать системные файлы", "Включает защищённые системные файлы (осторожно).", reg("HKCU", ADV, "ShowSuperHidden", 1, default=0), risky=True)
T(S, "ui_launchto", "Проводник открывается на «Этот компьютер»", "Вместо «Быстрого доступа».", reg("HKCU", ADV, "LaunchTo", 1, default=2))
T(S, "ui_classicmenu", "Классическое контекстное меню (Win11)", "Возвращает полное меню ПКМ. Перезапустите Проводник.",
  sh(r'reg add "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32" /f /ve',
     r'reg delete "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}" /f'))
T(S, "ui_tbleft", "Панель задач слева (Win11)", "Значки как в Windows 10.", reg("HKCU", ADV, "TaskbarAl", 0, default=1))
T(S, "ui_taskview", "Скрыть кнопку «Представление задач»", "Освобождает место на панели задач.", reg("HKCU", ADV, "ShowTaskViewButton", 0, default=1))
T(S, "ui_chat", "Скрыть кнопку Чат / Teams", "Убирает иконку чата.", reg("HKCU", ADV, "TaskbarMn", 0, default=1))
T(S, "ui_widgets", "Скрыть кнопку Виджетов", "Убирает иконку виджетов.", reg("HKCU", ADV, "TaskbarDa", 0, default=1))
T(S, "ui_search", "Скрыть поиск на панели задач", "Поиск доступен по Win+S.", reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Search", "SearchboxTaskbarMode", 0, default=2))
T(S, "ui_seconds", "Секунды в часах", "Показывать секунды в системных часах.", reg("HKCU", ADV, "ShowSecondsInSystemClock", 1, default=0))
T(S, "ui_shake", "Отключить Aero Shake", "Окна не сворачиваются при встряхивании.", reg("HKCU", ADV, "DisallowShaking", 1, default=0))
T(S, "ui_menudelay", "Мгновенное открытие меню", "MenuShowDelay = 0.", reg("HKCU", DSK, "MenuShowDelay", "0", "SZ", "400"))
T(S, "ui_shortcut", "Без «- Ярлык» в названии ярлыков", "Новые ярлыки создаются с чистым именем.", reg("HKCU", EXP, "link", "00000000", "BINARY"))
T(S, "ui_recent", "Отключить недавние файлы в быстром доступе", "Проводник не запоминает последние файлы и папки.", reg("HKCU", EXP, "ShowRecent", 0, default=1), reg("HKCU", EXP, "ShowFrequent", 0, default=1))
T(S, "ui_lockscreen", "Отключить экран блокировки", "Сразу показывать ввод пароля.", reg("HKLM", POL + r"\Personalization", "NoLockScreen", 1))
T(S, "ui_dark", "Тёмная тема", "Тёмная тема для приложений и системы.", reg("HKCU", PERS, "AppsUseLightTheme", 0, default=1), reg("HKCU", PERS, "SystemUsesLightTheme", 0, default=1))
T(S, "ui_startdelay", "Убрать задержку автозагрузки", "Программы автозагрузки стартуют без паузы.", reg("HKCU", EXP + r"\Serialize", "StartupDelayInMSec", 0))
T(S, "ui_startsound", "Отключить звук запуска Windows", "Без мелодии при включении.", reg("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "DisableStartupSound", 1, default=0))
T(S, "ui_autoplay", "Отключить автозапуск носителей", "Флешки и диски не запускаются сами.", reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\AutoplayHandlers", "DisableAutoplay", 1, default=0))

# ── Службы ──
S = "Службы"
T(S, "svc_sysmain", "SysMain (Superfetch)", "Предзагрузка программ в память — на SSD не нужна.", svc("SysMain", "auto"))
T(S, "svc_wsearch", "Windows Search (индексация)", "Отключает индексацию — поиск файлов станет медленнее.", svc("WSearch", "delayed-auto"))
T(S, "svc_diagtrack", "DiagTrack (телеметрия)", "Служба сбора диагностических данных.", svc("DiagTrack", "auto"))
T(S, "svc_dmwap", "dmwappushservice", "Служба маршрутизации push-сообщений WAP.", svc("dmwappushservice", "demand"))
T(S, "svc_fax", "Факс", "Служба факса — почти никому не нужна.", svc("Fax"))
T(S, "svc_maps", "Диспетчер карт", "Загрузка офлайн-карт.", svc("MapsBroker", "delayed-auto"))
T(S, "svc_retail", "Демонстрация розничной торговли", "Служба режима демо-витрины.", svc("RetailDemo"))
T(S, "svc_geo", "Геолокация (lfsvc)", "Определение местоположения.", svc("lfsvc"))
T(S, "svc_xbox", "Службы Xbox (4 шт.)", "Могут понадобиться для Xbox / Game Pass.", svc("XblAuthManager"), svc("XblGameSave"), svc("XboxNetApiSvc"), svc("XboxGipSvc"), risky=True)
T(S, "svc_phone", "Служба телефона", "Связь с телефоном (PhoneSvc).", svc("PhoneSvc"))
T(S, "svc_wmp", "Общий доступ к проигрывателю WMP", "Служба WMPNetworkSvc.", svc("WMPNetworkSvc"))
T(S, "svc_wer", "Служба отчётов об ошибках", "WerSvc.", svc("WerSvc"))
T(S, "svc_spooler", "Диспетчер печати", "Отключайте, только если не пользуетесь принтерами.", svc("Spooler", "auto"), risky=True)
T(S, "svc_bt", "Bluetooth", "Отключайте, только если не пользуетесь Bluetooth.", svc("bthserv"), risky=True)
T(S, "svc_bio", "Биометрия (Windows Hello)", "Отпечаток пальца и лицо перестанут работать.", svc("WbioSrvc"), risky=True)
T(S, "svc_hotspot", "Мобильный хот-спот", "Служба общего доступа к интернету (icssvc).", svc("icssvc"))
T(S, "svc_wisvc", "Служба Insider", "wisvc.", svc("wisvc"))
T(S, "svc_trk", "Отслеживание связей (TrkWks)", "Устаревшая служба отслеживания ярлыков.", svc("TrkWks", "auto"))
T(S, "svc_parental", "Родительский контроль", "WpcMonSvc.", svc("WpcMonSvc"))
T(S, "svc_semgr", "Диспетчер платежей и NFC", "SEMgrSvc.", svc("SEMgrSvc"))

# ── Питание ──
S = "Питание"
T(S, "pwr_ultimate", "План «Максимальная производительность»", "Создаёт и включает скрытую схему питания.", sh("powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 & powercfg -setactive e9a42b02-d5df-448d-aa00-03f14749eb61", "powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e"))
T(S, "pwr_usb", "Отключить USB selective suspend", "USB-устройства не «засыпают».", pc("2a737441-1930-4402-8d77-b2bebba308a3", "48e6b7a6-50f5-4782-a5d4-53bb8f07e226", 0, 1))
T(S, "pwr_pcie", "Отключить энергосбережение PCIe", "Link State Power Management — выкл. Лучше для видеокарты.", pc("SUB_PCIEXPRESS", "ASPM", 0, 1))
T(S, "pwr_disk", "Не выключать диск", "Диски всегда работают (от сети).", sh("powercfg -change -disk-timeout-ac 0", "powercfg -change -disk-timeout-ac 20"))
T(S, "pwr_sleep", "Не уходить в сон от сети", "Спящий режим выключен при питании от розетки.", sh("powercfg -change -standby-timeout-ac 0", "powercfg -change -standby-timeout-ac 30"))
T(S, "pwr_hybrid", "Отключить гибридный сон", "Не сохранять образ памяти при уходе в сон.", pc("SUB_SLEEP", "HYBRIDSLEEP", 0, 1))
T(S, "pwr_wake", "Запретить таймеры пробуждения", "Компьютер не просыпается сам по расписанию.", pc("SUB_SLEEP", "RTCWAKE", 0, 1))

# ── Очистка (разовые действия) ──
S = "Очистка"
T(S, "cln_temp", "Очистить временные файлы", "Удаляет содержимое папок TEMP пользователя и Windows.", sh(r'cmd /c "del /q /f /s %TEMP%\* & del /q /f /s C:\Windows\Temp\*"'), oneshot=True)
T(S, "cln_prefetch", "Очистить папку Prefetch", "Удаляет файлы предзагрузки.", sh(r'cmd /c "del /q /f /s C:\Windows\Prefetch\*"'), oneshot=True)
T(S, "cln_wu", "Очистить кэш Windows Update", "Удаляет скачанные, но не установленные обновления.", sh(r'net stop wuauserv & net stop bits & rd /s /q C:\Windows\SoftwareDistribution\Download & net start bits & net start wuauserv'), oneshot=True)
T(S, "cln_dns", "Сбросить кэш DNS", "ipconfig /flushdns.", sh("ipconfig /flushdns"), oneshot=True)
T(S, "cln_winsock", "Сбросить Winsock и IP", "Лечит проблемы с сетью. Нужна перезагрузка.", sh("netsh winsock reset & netsh int ip reset"), oneshot=True)
T(S, "cln_recycle", "Очистить корзину", "Удаляет всё из корзины на всех дисках.", ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue"), oneshot=True)
T(S, "cln_dism", "Очистка компонентов Windows (DISM)", "Удаляет старые версии обновлений. Может идти несколько минут.", sh("Dism.exe /online /Cleanup-Image /StartComponentCleanup"), oneshot=True)
T(S, "cln_explorer", "Перезапустить Проводник", "Применяет изменения интерфейса без перезагрузки.", sh("taskkill /f /im explorer.exe & start explorer.exe"), oneshot=True)

SECTIONS = []
for _t in TWEAKS:
    if _t.section not in SECTIONS:
        SECTIONS.append(_t.section)


# ───────────────────────── применение / откат / состояние ─────────────────────────
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            d.setdefault("applied", {})
            return d
    except Exception:
        return {"applied": {}}


def save_state(st):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def is_active(t, st):
    if t.oneshot:
        return False
    regs = [a for a in t.actions if a[0] == "reg"]
    if regs and len(regs) == len(t.actions):
        return all(reg_matches(a) for a in regs)
    return t.id in st["applied"]


def _enc(v):
    return ["b", bytes(v).hex()] if isinstance(v, (bytes, bytearray)) else ["v", v]


def _dec(e):
    return bytes.fromhex(e[1]) if e[0] == "b" else e[1]


def apply_tweak(t, st, log):
    backups = [] if t.id in st["applied"] else None
    fresh = []
    for a in t.actions:
        if a[0] == "reg":
            _, hive, path, name, rtype, val, _d = a
            ex, typ, old = reg_read(hive, path, name)
            fresh.append([hive, path, name, ex, typ, _enc(old) if ex else None])
            reg_write(hive, path, name, rtype, val)
        else:
            code, out = run(a[1], ps=(a[0] == "ps"))
            if code != 0:
                log(f"   ! код {code}: {out.strip()[:160]}")
    if backups is None:
        st["applied"][t.id] = {"backup": fresh}
    save_state(st)


def revert_tweak(t, st, log):
    bk = {tuple(b[:3]): b for b in st["applied"].get(t.id, {}).get("backup", [])}
    for a in t.actions:
        if a[0] == "reg":
            _, hive, path, name, rtype, val, default = a
            b = bk.get((hive, path, name))
            if b:
                if b[3]:
                    reg_write(hive, path, name, {winreg.REG_DWORD: "DWORD", winreg.REG_BINARY: "BINARY"}.get(b[4], "SZ"), _dec(b[5]))
                else:
                    reg_delete(hive, path, name)
            elif default is not None:
                reg_write(hive, path, name, rtype, default)
            else:
                reg_delete(hive, path, name)
        elif a[2]:
            code, out = run(a[2], ps=(a[0] == "ps"))
            if code != 0:
                log(f"   ! код {code}: {out.strip()[:160]}")
    st["applied"].pop(t.id, None)
    save_state(st)


def create_restore_point():
    run('Enable-ComputerRestore -Drive "$env:SystemDrive\\"', ps=True)
    return run('Checkpoint-Computer -Description "Wexxyy Tweaker" -RestorePointType MODIFY_SETTINGS', ps=True)


# ───────────────────────── сеть: пинг и DNS ─────────────────────────
REGIONS = {
    "eu-central-1": ("FRANKFURT", "DE"), "eu-west-1": ("IRELAND", "IE"), "eu-west-2": ("LONDON", "GB"),
    "eu-west-3": ("PARIS", "FR"), "eu-north-1": ("STOCKHOLM", "SE"),
    "us-east-1": ("VIRGINIA", "US"), "us-east-2": ("OHIO", "US"),
    "us-west-1": ("CALIFORNIA", "US"), "us-west-2": ("OREGON", "US"),
    "ap-northeast-1": ("TOKYO", "JP"), "ap-northeast-2": ("SEOUL", "KR"), "ap-southeast-1": ("SINGAPORE", "SG"),
    "ap-southeast-2": ("SYDNEY", "AU"), "ap-south-1": ("MUMBAI", "IN"), "sa-east-1": ("SAO PAULO", "BR"),
}
_EU = ["eu-central-1", "eu-west-2", "eu-west-3", "eu-north-1", "eu-west-1"]
GAMES = {
    "Fortnite — EU": _EU,
    "Fortnite — NA East": ["us-east-1", "us-east-2"],
    "Fortnite — NA West": ["us-west-1", "us-west-2"],
    "Fortnite — Asia": ["ap-northeast-1", "ap-northeast-2", "ap-southeast-1"],
    "CS2 — EU": _EU, "Valorant — EU": _EU, "Dota 2 — EU": _EU,
    "Apex Legends — EU": _EU, "Warzone — EU": _EU, "League of Legends — EUW": _EU,
    "Любая игра — весь мир": list(REGIONS),
}
DNS_SERVERS = [("Cloudflare", "1.1.1.1", "1.0.0.1"), ("Google", "8.8.8.8", "8.8.4.4"),
               ("Quad9", "9.9.9.9", "149.112.112.112"), ("OpenDNS", "208.67.222.222", "208.67.220.220"),
               ("AdGuard", "94.140.14.14", "94.140.15.15")]


def tcp_ping(host, port=443, n=5, timeout=1.5, stop=None):
    import socket, time
    try:
        ip = socket.gethostbyname(host)
    except OSError:
        return {"avg": None, "min": None, "jitter": None, "loss": 100}
    ts, fails = [], 0
    for _ in range(n):
        if stop is not None and stop.is_set():
            break
        t0 = time.perf_counter()
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            ts.append((time.perf_counter() - t0) * 1000)
            s.close()
        except OSError:
            fails += 1
        time.sleep(0.05)
    sent = len(ts) + fails
    if not ts:
        return {"avg": None, "min": None, "jitter": None, "loss": 100}
    jitter = sum(abs(a - b) for a, b in zip(ts, ts[1:])) / (len(ts) - 1) if len(ts) > 1 else 0.0
    return {"avg": sum(ts) / len(ts), "min": min(ts), "jitter": jitter, "loss": round(100 * fails / sent)}


def dns_packet(name, rid):
    q = struct.pack(">HHHHHH", rid, 0x0100, 1, 0, 0, 0)
    q += b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    return q + struct.pack(">HH", 1, 1)


def dns_ping(server, timeout=1.5):
    import socket, time, random, statistics
    vals = []
    for name in ("example.com", "wikipedia.org", "microsoft.com"):
        rid = random.randint(0, 65535)
        pkt = dns_packet(name, rid)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        try:
            t0 = time.perf_counter()
            s.sendto(pkt, (server, 53))
            data = s.recv(512)
            dt = (time.perf_counter() - t0) * 1000
            if data[:2] == pkt[:2]:
                vals.append(dt)
        except OSError:
            pass
        finally:
            s.close()
    return statistics.median(vals) if vals else None


def set_dns(primary, secondary):
    return run(f"Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object {{ Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses ('{primary}','{secondary}') }}", ps=True)


def reset_dns():
    return run("Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses }", ps=True)


# ───────────────────────── настройки внешнего вида ─────────────────────────
UI_FILE = os.path.join(DATA_DIR, "ui.json")
DARK = dict(bg="#0c0d10", side="#101114", card="#14161a", card2="#1a1d22", line="#262930", text="#e9ebf0", muted="#7d8493", ok="#34e0a1", bad="#f2616a", warn="#f5b84a", dark=True)
LIGHT = dict(bg="#eef0f5", side="#ffffff", card="#ffffff", card2="#e9ecf2", line="#d3d8e2", text="#14161c", muted="#6b7280", ok="#12a36b", bad="#d94452", warn="#c78a12", dark=False)
PRESETS = {
    "Неон (зелёный)": (DARK, "#34e0a1"), "Фиолетовый": (DARK, "#8b6cff"), "Красный": (DARK, "#ff5a6a"),
    "Синий": (DARK, "#4aa3ff"), "Оранжевый": (DARK, "#ff9a3d"), "Розовый": (DARK, "#ff6bc1"),
    "Светлая": (LIGHT, "#5b3df5"),
}
ACCENTS = ["#34e0a1", "#8b6cff", "#ff5a6a", "#4aa3ff", "#ff9a3d", "#ff6bc1", "#f5d90a", "#00d1ff"]
DEFAULT_UI = {"preset": "Неон (зелёный)", "accent": None, "scale": 1.0, "radius": 12, "alpha": 1.0, "desc": True, "compact": False}
SCALE_OPTS = {"Маленький": 0.9, "Обычный": 1.0, "Крупный": 1.15}
RAD_OPTS = {"Острые": 4, "Средние": 12, "Круглые": 20}


def load_ui():
    u = dict(DEFAULT_UI)
    try:
        with open(UI_FILE, "r", encoding="utf-8") as f:
            u.update({k: v for k, v in json.load(f).items() if k in DEFAULT_UI})
    except Exception:
        pass
    return u


def save_ui(u):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(UI_FILE, "w", encoding="utf-8") as f:
            json.dump(u, f, ensure_ascii=False)
    except Exception:
        pass


def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(c1, c2, t):
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def valid_hex(s):
    s = (s or "").strip()
    if len(s) == 7 and s[0] == "#":
        try:
            int(s[1:], 16)
            return True
        except ValueError:
            return False
    return False


def build_theme(u):
    base, acc = PRESETS.get(u.get("preset"), PRESETS["Неон (зелёный)"])
    th = dict(base)
    acc = u.get("accent") if valid_hex(u.get("accent")) else acc
    r, g, b = _rgb(acc)
    th["accent"] = acc
    th["accent_h"] = mix(acc, "#000000", 0.18)
    th["on_accent"] = "#0b0d10" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"
    th["nav_text"] = mix(th["muted"], th["text"], 0.55)
    return th


def _import_ctk():
    try:
        import customtkinter as ctk
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "customtkinter"], creationflags=NO_WINDOW)
        import customtkinter as ctk
    return ctk


# ───────────────────────── интерфейс ─────────────────────────
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    if getattr(sys, "frozen", False):
        exe = sys.executable
        params = " ".join('"%s"' % a for a in sys.argv[1:])
    else:
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        exe = pyw if os.path.exists(pyw) else sys.executable
        params = " ".join('"%s"' % a for a in [os.path.abspath(sys.argv[0])] + sys.argv[1:])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)


STEPS = ["ПРОВЕРКА СЕТИ", "ДОСТУП К УЗЛАМ", "КАЧЕСТВО СВЯЗИ", "ЛУЧШИЙ МАРШРУТ"]


def launch_ui():
    import tkinter as tk
    from tkinter import messagebox
    import functools
    ctk = _import_ctk()

    class App(ctk.CTk):
        def __init__(self):
            ui0 = load_ui()
            th0 = build_theme(ui0)
            ctk.set_appearance_mode("dark" if th0["dark"] else "light")
            super().__init__()
            self.ui, self.th = ui0, th0
            self.title(APP)
            self.geometry("1200x780")
            self.minsize(1040, 700)
            try:
                self.attributes("-alpha", float(self.ui["alpha"]))
            except Exception:
                pass
            ico = ensure_icon()
            self.after(250, lambda: self._set_icon(ico))
            self.protocol("WM_DELETE_WINDOW", self._close)
            self.st = load_state()
            self.vars = {t.id: tk.IntVar(value=1 if is_active(t, self.st) else 0) for t in TWEAKS}
            self.game_var = tk.StringVar(value=list(GAMES)[0])
            self.query = tk.StringVar(value="")
            self.opt_vars = {}
            self.q = queue.Queue()
            self.log_lines = []
            self.last_msg = "Готово. Отметьте твики переключателями и нажмите «Применить»."
            self.busy = False
            self.page = "home"
            self.logbox = None
            self.pill_lbl = None
            self.msg_lbl = None
            self.status = {}
            self.nav = {}
            self.search_job = None
            self.ping = {"running": False, "stop": None, "results": {}, "steps": [0, 0, 0, 0], "best": None,
                         "status": "ГОТОВ К ПРОВЕРКЕ", "dns": {}}
            self.step_lbls, self.step_cells = [], []
            self._build()
            self.show("home")
            self.after(100, self._poll)
            flag = os.path.join(DATA_DIR, ".shortcut_asked")
            if not os.path.exists(flag):
                os.makedirs(DATA_DIR, exist_ok=True)
                open(flag, "w").close()
                if messagebox.askyesno(APP, "Создать ярлык с иконкой W на рабочем столе?"):
                    self.make_shortcut()

        # ---------- общие помощники ----------
        def _set_icon(self, ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        def _close(self):
            save_ui(self.ui)
            self.destroy()

        @property
        def R(self):
            return int(self.ui["radius"])

        def F(self, size, bold=False):
            return ctk.CTkFont(family="Segoe UI", size=max(9, int(round(size * float(self.ui["scale"])))), weight="bold" if bold else "normal")

        def card(self, parent):
            th = self.th
            return ctk.CTkFrame(parent, fg_color=th["card"], corner_radius=self.R, border_width=1, border_color=th["line"])

        def label(self, parent, text, size=12, bold=False, color=None, **kw):
            return ctk.CTkLabel(parent, text=text, font=self.F(size, bold), text_color=color or self.th["text"], **kw)

        def btn(self, parent, text, cmd, kind="ghost", width=None, height=38):
            th = self.th
            style = {
                "accent": (th["accent"], th["accent_h"], th["on_accent"]),
                "bad": (th["bad"], mix(th["bad"], "#000000", 0.18), "#ffffff"),
                "ghost": (th["card2"], th["line"], th["text"]),
            }[kind]
            kw = {"width": width} if width else {}
            return ctk.CTkButton(parent, text=text, command=cmd, fg_color=style[0], hover_color=style[1], text_color=style[2],
                                 corner_radius=self.R, height=height, font=self.F(12, True), **kw)

        def alive(self, w):
            try:
                return w is not None and bool(w.winfo_exists())
            except Exception:
                return False

        # ---------- каркас окна ----------
        def _build(self):
            th = self.th
            for w in self.winfo_children():
                w.destroy()
            self.configure(fg_color=th["bg"])
            self.grid_columnconfigure(1, weight=1)
            self.grid_rowconfigure(0, weight=1)
            side = ctk.CTkFrame(self, fg_color=th["side"], corner_radius=0, width=240)
            side.grid(row=0, column=0, sticky="nsew")
            side.grid_propagate(False)
            logo = ctk.CTkFrame(side, fg_color="transparent")
            logo.pack(fill="x", padx=16, pady=(18, 14))
            ctk.CTkLabel(logo, text="W", width=36, height=36, fg_color=th["accent"], text_color=th["on_accent"],
                         corner_radius=min(self.R, 12), font=self.F(18, True)).pack(side="left")
            self.label(logo, "WEXXYY TWEAKER", 13, True).pack(side="left", padx=10)

            self.nav = {}
            self.nav_btn(side, "look", "ВНЕШНИЙ ВИД", bottom=True)
            self.nav_btn(side, "home", "ГЛАВНАЯ")
            self.nav_btn(side, "ping", "БУСТЕР ПИНГА")
            self.label(side, "КАТЕГОРИИ", 11, True, th["muted"], anchor="w").pack(fill="x", padx=22, pady=(14, 4))
            for sec in SECTIONS:
                self.nav_btn(side, "sec:" + sec, sec.upper())

            self.content = ctk.CTkFrame(self, fg_color="transparent")
            self.content.grid(row=0, column=1, sticky="nsew", padx=22, pady=(18, 10))
            self.content.grid_columnconfigure(0, weight=1)
            self.content.grid_rowconfigure(1, weight=1)

        def nav_btn(self, parent, key, text, bottom=False):
            th = self.th
            b = ctk.CTkButton(parent, text=text, anchor="w", height=34, corner_radius=self.R, fg_color="transparent",
                              hover_color=th["card2"], text_color=th["nav_text"], font=self.F(12, True),
                              command=lambda k=key: self.show(k))
            if bottom:
                b.pack(side="bottom", fill="x", padx=12, pady=(2, 16))
            else:
                b.pack(fill="x", padx=12, pady=1)
            self.nav[key] = b

        def show(self, key):
            th = self.th
            self.page = key
            self.status = {}
            self.logbox = None
            for k, b in self.nav.items():
                on = k == key
                b.configure(fg_color=th["card2"] if on else "transparent", text_color=th["text"] if on else th["nav_text"])
            for w in self.content.winfo_children():
                w.destroy()
            titles = {"home": "ГЛАВНАЯ", "ping": "БУСТЕР ПИНГА", "look": "ВНЕШНИЙ ВИД"}
            title = titles.get(key, key.split(":", 1)[-1].upper())
            pill = self.pill_text(key)
            head = ctk.CTkFrame(self.content, fg_color="transparent")
            head.grid(row=0, column=0, sticky="ew", pady=(0, 14))
            self.label(head, title, 22, True).pack(side="left")
            pf = ctk.CTkFrame(head, fg_color="transparent", border_width=1, border_color=th["ok"], corner_radius=16)
            pf.pack(side="right")
            self.pill_lbl = self.label(pf, pill, 11, True, th["ok"])
            self.pill_lbl.pack(padx=14, pady=5)
            self.body = ctk.CTkFrame(self.content, fg_color="transparent")
            self.body.grid(row=1, column=0, sticky="nsew")
            self.msg_lbl = self.label(self.content, self.last_msg, 11, False, th["muted"], anchor="w")
            self.msg_lbl.grid(row=2, column=0, sticky="ew", pady=(8, 0))
            if key == "home":
                self.page_home()
            elif key == "ping":
                self.page_ping()
            elif key == "look":
                self.page_look()
            else:
                self.page_tweaks(key.split(":", 1)[1])

        def pill_text(self, key):
            if key == "home":
                return f"ВСЕГО ТВИКОВ: {len(TWEAKS)}"
            if key == "ping":
                return self.ping["status"]
            if key == "look":
                return "ТЕМА: " + self.ui["preset"].upper()
            sec = key.split(":", 1)[1]
            items = [t for t in TWEAKS if t.section == sec]
            if sec == "Очистка":
                return f"ДЕЙСТВИЙ: {len(items)}"
            n = sum(1 for t in items if is_active(t, self.st))
            return f"ВКЛЮЧЕНО: {n}/{len(items)}"

        def scroll(self, parent):
            th = self.th
            sf = ctk.CTkScrollableFrame(parent, fg_color="transparent", scrollbar_button_color=th["line"],
                                        scrollbar_button_hover_color=th["muted"])
            sf.pack(fill="both", expand=True)
            return sf

        # ---------- журнал и очередь ----------
        def log(self, msg):
            self.q.put(msg)

        def refresh_page(self):
            self.show(self.page)

        def _poll(self):
            try:
                while True:
                    m = self.q.get_nowait()
                    if callable(m):
                        try:
                            m()
                        except Exception:
                            pass
                    elif m == "__DONE__":
                        self.busy = False
                        self.refresh_page()
                    else:
                        self.log_lines.append(m)
                        self.log_lines = self.log_lines[-300:]
                        self.last_msg = m
                        if self.alive(self.msg_lbl):
                            self.msg_lbl.configure(text=m)
                        if self.alive(self.logbox):
                            self.logbox.configure(state="normal")
                            self.logbox.insert("end", m + "\n")
                            self.logbox.see("end")
                            self.logbox.configure(state="disabled")
            except queue.Empty:
                pass
            self.after(100, self._poll)

        # ---------- главная ----------
        def page_home(self):
            th = self.th
            sf = self.scroll(self.body)
            active = sum(1 for t in TWEAKS if is_active(t, self.st))
            row = ctk.CTkFrame(sf, fg_color="transparent")
            row.pack(fill="x", pady=(0, 12))
            for i, (lab, val, col) in enumerate([("ВСЕГО ТВИКОВ", len(TWEAKS), th["text"]), ("АКТИВНО СЕЙЧАС", active, th["ok"]), ("РАЗДЕЛОВ", len(SECTIONS), th["text"])]):
                row.grid_columnconfigure(i, weight=1, uniform="h")
                c = self.card(row)
                c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 6 if i == 2 else 0))
                self.label(c, lab, 11, True, th["muted"], anchor="w").pack(fill="x", padx=18, pady=(14, 0))
                self.label(c, str(val), 30, True, col, anchor="w").pack(fill="x", padx=18, pady=(0, 14))
            c = self.card(sf)
            c.pack(fill="x", pady=(0, 12), padx=(0, 6))
            self.label(c, "БЫСТРЫЕ ДЕЙСТВИЯ", 11, True, th["muted"], anchor="w").pack(fill="x", padx=18, pady=(14, 8))
            br = ctk.CTkFrame(c, fg_color="transparent")
            br.pack(fill="x", padx=14, pady=(0, 6))
            for i, (t, cmd, k) in enumerate([("ПРИМЕНИТЬ ВЫБРАННОЕ", self.apply_selected, "accent"), ("ВЫБРАТЬ БЕЗОПАСНЫЕ ВЕЗДЕ", self.select_safe_all, "ghost"),
                                             ("ТОЧКА ВОССТАНОВЛЕНИЯ", self.restore_point, "ghost"), ("ЯРЛЫК С ИКОНКОЙ W", self.make_shortcut, "ghost")]):
                br.grid_columnconfigure(i % 2, weight=1, uniform="b")
                self.btn(br, t, cmd, k).grid(row=i // 2, column=i % 2, sticky="ew", padx=4, pady=4)
            self.label(c, "Перед массовым применением создайте точку восстановления. Применяется всё, что отмечено во всех разделах.", 11, False, th["muted"], anchor="w", justify="left", wraplength=700).pack(fill="x", padx=18, pady=(2, 14))
            c2 = self.card(sf)
            c2.pack(fill="x", pady=(0, 12), padx=(0, 6))
            self.label(c2, "ЖУРНАЛ", 11, True, th["muted"], anchor="w").pack(fill="x", padx=18, pady=(14, 6))
            self.logbox = ctk.CTkTextbox(c2, height=260, fg_color=th["bg"], text_color=th["muted"], font=ctk.CTkFont(family="Consolas", size=12),
                                         corner_radius=self.R, border_width=0)
            self.logbox.pack(fill="x", padx=14, pady=(0, 14))
            self.logbox.insert("end", "\n".join(self.log_lines) + ("\n" if self.log_lines else ""))
            self.logbox.configure(state="disabled")

        # ---------- разделы с твиками ----------
        def page_tweaks(self, sec):
            th = self.th
            self.cur_sec = sec
            self.body.grid_rowconfigure(1, weight=1)
            self.body.grid_columnconfigure(0, weight=1)
            bar = ctk.CTkFrame(self.body, fg_color="transparent")
            bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
            e = ctk.CTkEntry(bar, textvariable=self.query, placeholder_text="ПОИСК ПО ВСЕМ ТВИКАМ", width=300, height=36,
                             fg_color=th["card"], border_color=th["line"], text_color=th["text"], corner_radius=self.R)
            e.pack(side="right")
            e.bind("<KeyRelease>", lambda _e: self._debounce())
            self.list_holder = ctk.CTkFrame(self.body, fg_color="transparent")
            self.list_holder.grid(row=1, column=0, sticky="nsew")
            act = ctk.CTkFrame(self.body, fg_color="transparent")
            act.grid(row=2, column=0, sticky="ew", pady=(10, 0))
            self.btn(act, "ПРИМЕНИТЬ ВЫБРАННОЕ", self.apply_selected, "accent", width=260, height=42).pack(side="left")
            self.btn(act, "ВЫБРАТЬ БЕЗОПАСНЫЕ", self.select_safe, "ghost", width=190, height=42).pack(side="left", padx=8)
            self.btn(act, "СНЯТЬ ВЫБОР", self.clear_section, "ghost", width=140, height=42).pack(side="left")
            self.render_list()

        def _debounce(self):
            if self.search_job:
                self.after_cancel(self.search_job)
            self.search_job = self.after(250, self.render_list)

        def render_list(self):
            if not self.alive(getattr(self, "list_holder", None)):
                return
            for w in self.list_holder.winfo_children():
                w.destroy()
            self.status = {}
            q = self.query.get().strip().lower()
            if q:
                items = [t for t in TWEAKS if q in t.name.lower() or q in t.desc.lower()]
            else:
                items = [t for t in TWEAKS if t.section == self.cur_sec]
            sf = self.scroll(self.list_holder)
            if not items:
                self.label(sf, "Ничего не найдено", 13, False, self.th["muted"]).pack(pady=30)
                return
            for t in items[:40]:
                self._row(sf, t)
            if len(items) > 40:
                self.label(sf, f"Показаны первые 40 из {len(items)} — уточните запрос", 11, False, self.th["muted"]).pack(pady=8)

        def _row(self, parent, t):
            th = self.th
            compact = bool(self.ui["compact"])
            f = ctk.CTkFrame(parent, fg_color=th["card"], corner_radius=self.R, border_width=1, border_color=th["line"])
            f.pack(fill="x", pady=3 if compact else 4, padx=(0, 6))
            f.grid_columnconfigure(1, weight=1)
            sw = ctk.CTkSwitch(f, text="", variable=self.vars[t.id], width=46, progress_color=th["accent"], fg_color=th["line"],
                               button_color="#ffffff", button_hover_color="#e6e6e6")
            sw.grid(row=0, column=0, rowspan=2, padx=(14, 6), pady=6 if compact else 10)
            tf = ctk.CTkFrame(f, fg_color="transparent")
            tf.grid(row=0, column=1, sticky="w", pady=(6 if compact else 10, 0))
            self.label(tf, t.name, 13, True).pack(side="left")
            if t.risky:
                self.label(tf, "   РИСКОВАННО", 11, True, th["bad"]).pack(side="left")
            if self.ui["desc"]:
                self.label(f, t.desc, 11, False, th["muted"], anchor="w", justify="left", wraplength=520).grid(
                    row=1, column=1, sticky="w", pady=(0, 6 if compact else 10))
            st = self.label(f, "", 11, True, th["muted"], width=110)
            st.grid(row=0, column=2, rowspan=2, padx=14)
            self.status[t.id] = st
            if t.oneshot:
                st.configure(text="РАЗОВО")
            else:
                on = is_active(t, self.st)
                st.configure(text="● АКТИВНО" if on else "○ ВЫКЛЮЧЕНО", text_color=th["ok"] if on else th["muted"])

        def select_safe(self):
            sec = getattr(self, "cur_sec", None)
            for t in TWEAKS:
                if (sec is None or t.section == sec) and not t.risky and not t.oneshot:
                    self.vars[t.id].set(1)

        def select_safe_all(self):
            for t in TWEAKS:
                if not t.risky and not t.oneshot:
                    self.vars[t.id].set(1)
            self.log("Выбраны все безопасные твики. Нажмите «Применить выбранное».")

        def clear_section(self):
            sec = getattr(self, "cur_sec", None)
            for t in TWEAKS:
                if sec is None or t.section == sec:
                    self.vars[t.id].set(0)

        # ---------- применение ----------
        def apply_selected(self):
            if self.busy:
                self.log("Подождите, предыдущая операция ещё идёт.")
                return
            jobs = []
            for t in TWEAKS:
                want, cur = bool(self.vars[t.id].get()), is_active(t, self.st)
                if t.oneshot and want:
                    jobs.append(("run", t))
                elif want and not cur:
                    jobs.append(("apply", t))
                elif not want and cur:
                    jobs.append(("revert", t))
            if not jobs:
                self.log("Нечего применять: состояние уже совпадает с выбором.")
                return
            risky = [t.name for k, t in jobs if k in ("apply", "run") and t.risky]
            if risky and not messagebox.askyesno(APP, "Среди выбранного есть рискованные твики:\n\n• " + "\n• ".join(risky) + "\n\nПродолжить?"):
                return
            self.busy = True
            threading.Thread(target=self._worker, args=(jobs,), daemon=True).start()

        def _worker(self, jobs):
            for kind, t in jobs:
                try:
                    if kind == "revert":
                        self.log(f"↩ Откат: {t.name}")
                        revert_tweak(t, self.st, self.log)
                    else:
                        self.log(f"▶ {'Выполняю' if kind == 'run' else 'Применяю'}: {t.name}")
                        apply_tweak(t, self.st, self.log)
                    if t.oneshot:
                        self.q.put(functools.partial(self.vars[t.id].set, 0))
                except Exception as e:
                    self.log(f"   ✖ ошибка: {e}")
            self.log("Готово. Для части твиков нужна перезагрузка.")
            self.q.put("__DONE__")

        def restore_point(self):
            if self.busy:
                return
            self.busy = True
            self.log("Создаю точку восстановления…")

            def w():
                code, out = create_restore_point()
                self.log("Точка восстановления создана." if code == 0 else "Не удалось создать точку (защита системы выключена или лимит 1 раз в 24 ч).")
                self.q.put("__DONE__")
            threading.Thread(target=w, daemon=True).start()

        def make_shortcut(self):
            ok = create_desktop_shortcut()
            self.log("Ярлык с иконкой W создан на рабочем столе." if ok else "Не удалось создать ярлык.")

        # ---------- бустер пинга ----------
        def page_ping(self):
            th = self.th
            P = self.ping
            sf = self.scroll(self.body)
            c1 = self.card(sf)
            c1.pack(fill="x", pady=(0, 12), padx=(0, 6))
            top = ctk.CTkFrame(c1, fg_color="transparent")
            top.pack(fill="x", padx=18, pady=(16, 8))
            ctk.CTkOptionMenu(top, values=list(GAMES), variable=self.game_var, width=270, height=40, fg_color=th["card2"],
                              button_color=th["line"], button_hover_color=th["muted"], text_color=th["text"],
                              dropdown_fg_color=th["card"], dropdown_text_color=th["text"], dropdown_hover_color=th["card2"],
                              corner_radius=self.R, font=self.F(12, True), dropdown_font=self.F(12),
                              command=lambda v: self.ping_reset_view()).pack(side="left")
            self.ping_btn = self.btn(top, "ОСТАНОВИТЬ" if P["running"] else "ЗАПУСТИТЬ ПРОВЕРКУ", self.ping_toggle,
                                     "bad" if P["running"] else "accent", width=250, height=42)
            self.ping_btn.pack(side="right")
            st = ctk.CTkFrame(c1, fg_color="transparent")
            st.pack(fill="x", padx=14, pady=(4, 16))
            self.step_lbls, self.step_cells = [], []
            for i, name in enumerate(STEPS):
                st.grid_columnconfigure(i, weight=1, uniform="s")
                cell = ctk.CTkFrame(st, fg_color=th["card2"], corner_radius=self.R)
                cell.grid(row=0, column=i, padx=4, sticky="ew")
                lb = self.label(cell, name, 11, True, th["muted"])
                lb.pack(pady=15)
                self.step_lbls.append(lb)
                self.step_cells.append(cell)
            c2 = self.card(sf)
            c2.pack(fill="x", pady=(0, 12), padx=(0, 6))
            hr = ctk.CTkFrame(c2, fg_color="transparent")
            hr.pack(fill="x", padx=18, pady=(14, 0))
            self.label(hr, "ИГРОВОЙ МАРШРУТ", 11, True, th["muted"]).pack(side="left")
            self.route_state = self.label(hr, "", 11, True, th["ok"])
            self.route_state.pack(side="right")
            self.canvas = tk.Canvas(c2, width=700, height=230, bg=th["card"], highlightthickness=0)
            self.canvas.pack(pady=(4, 14))
            c3 = self.card(sf)
            c3.pack(fill="x", pady=(0, 12), padx=(0, 6))
            self.label(c3, "ВСЕ УЗЛЫ РЕГИОНА", 11, True, th["muted"], anchor="w").pack(fill="x", padx=18, pady=(14, 6))
            self.res_frame = ctk.CTkFrame(c3, fg_color="transparent")
            self.res_frame.pack(fill="x", padx=18, pady=(0, 14))
            c4 = self.card(sf)
            c4.pack(fill="x", pady=(0, 12), padx=(0, 6))
            dh = ctk.CTkFrame(c4, fg_color="transparent")
            dh.pack(fill="x", padx=18, pady=(14, 6))
            self.label(dh, "ПОДБОР DNS", 11, True, th["muted"]).pack(side="left")
            self.btn(dh, "СБРОСИТЬ", self.dns_reset_click, "ghost", width=110, height=32).pack(side="right")
            self.btn(dh, "ПРИМЕНИТЬ ЛУЧШИЙ", self.dns_apply_click, "ghost", width=170, height=32).pack(side="right", padx=6)
            self.btn(dh, "ПРОВЕРИТЬ DNS", self.dns_test_click, "accent", width=150, height=32).pack(side="right")
            self.dns_frame = ctk.CTkFrame(c4, fg_color="transparent")
            self.dns_frame.pack(fill="x", padx=18, pady=(0, 14))
            self.label(sf, "Замеряется реальная задержка (TCP) до дата-центров региона и скорость DNS-серверов, чтобы выбрать лучший регион и DNS. "
                           "Трафик игры через сторонние серверы не перенаправляется — для этого нужен VPN или туннель.",
                       11, False, th["muted"], anchor="w", justify="left", wraplength=720).pack(fill="x", padx=4, pady=(0, 10))
            self.ping_paint_steps()
            self.ping_draw()
            self.ping_render_rows()
            self.dns_render()

        def ping_reset_view(self):
            P = self.ping
            if P["running"]:
                return
            P["results"], P["steps"], P["best"] = {}, [0, 0, 0, 0], None
            self.ping_set_status("ГОТОВ К ПРОВЕРКЕ")
            self.ping_paint_steps()
            self.ping_draw()
            self.ping_render_rows()

        def ping_set_status(self, text):
            self.ping["status"] = text
            if self.page == "ping" and self.alive(self.pill_lbl):
                self.pill_lbl.configure(text=text)

        def ping_paint_steps(self):
            th = self.th
            for i, lb in enumerate(self.step_lbls):
                if not self.alive(lb):
                    continue
                s = self.ping["steps"][i]
                col = {0: th["muted"], 1: th["accent"], 2: th["ok"], -1: th["bad"]}[s]
                lb.configure(text_color=col, text=("✓ " if s == 2 else "… " if s == 1 else "✕ " if s == -1 else "") + STEPS[i])

        def ping_sorted(self):
            res = self.ping["results"]
            ok = sorted([(r, v) for r, v in res.items() if v["avg"] is not None], key=lambda x: x[1]["avg"])
            bad = [(r, v) for r, v in res.items() if v["avg"] is None]
            return ok, bad

        def ping_refresh(self):
            if self.page != "ping":
                return
            self.ping_paint_steps()
            self.ping_draw()
            self.ping_render_rows()

        def ping_draw(self):
            c = getattr(self, "canvas", None)
            if not self.alive(c):
                return
            th = self.th
            P = self.ping
            c.delete("all")
            game = self.game_var.get()
            ok, bad = self.ping_sorted()
            nodes = [(r, v["avg"]) for r, v in ok[:2]]
            for r in GAMES[game]:
                if len(nodes) >= 2:
                    break
                if r not in [n[0] for n in nodes]:
                    nodes.append((r, None))
            ys = [62, 168]

            def rr(x1, y1, x2, y2, r, **kw):
                pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
                return c.create_polygon(pts, smooth=True, **kw)

            c.create_oval(30, 80, 90, 140, outline=th["ok"], width=2)
            c.create_oval(52, 92, 68, 108, outline=th["ok"], width=2)
            c.create_arc(44, 110, 76, 140, start=0, extent=180, style="arc", outline=th["ok"], width=2)
            c.create_text(60, 160, text="ВЫ", fill=th["muted"], font=("Segoe UI", 9, "bold"))
            gx = 600
            rr(gx, 80, gx + 62, 142, 14, fill="#2b6cff", outline="")
            c.create_text(gx + 31, 111, text=game[0], fill="#ffffff", font=("Segoe UI", 26, "bold"))
            c.create_text(gx + 31, 160, text=game.split(" — ")[0].upper(), fill=th["muted"], font=("Segoe UI", 9, "bold"))
            for i, (r, ms) in enumerate(nodes):
                y = ys[i]
                best = i == 0 and ms is not None
                col = th["ok"] if best else th["line"]
                c.create_line(90, 110, 140, 110, 140, y, 255, y, smooth=True, fill=col, width=2)
                c.create_line(425, y, 500, y, 500, 110, gx, 110, smooth=True, fill=col, width=2)
                rr(255, y - 36, 425, y + 36, 12, fill=th["card2"], outline=col, width=2 if best else 1)
                name, cc = REGIONS[r]
                c.create_text(340, y - 18, text=f"{name}  ·  {cc}", fill=th["text"], font=("Segoe UI", 10, "bold"))
                c.create_text(340, y + 8, text=f"{round(ms)} MS" if ms is not None else "— MS", fill=th["ok"] if best else th["muted"], font=("Segoe UI", 11, "bold"))
                if best:
                    c.create_text(340, y + 26, text="ЛУЧШИЙ", fill=th["ok"], font=("Segoe UI", 8, "bold"))
            if len(nodes) == 2:
                c.create_text(340, 115, text="+", fill=th["muted"], font=("Segoe UI", 14, "bold"))
            if self.alive(self.route_state):
                if P["running"]:
                    self.route_state.configure(text="● ПРОВЕРКА", text_color=th["accent"])
                elif P["best"]:
                    self.route_state.configure(text="● МАРШРУТ ВЫБРАН", text_color=th["ok"])
                else:
                    self.route_state.configure(text="● ОЖИДАНИЕ", text_color=th["muted"])

        def ping_render_rows(self):
            fr = getattr(self, "res_frame", None)
            if not self.alive(fr):
                return
            th = self.th
            for w in fr.winfo_children():
                w.destroy()
            ok, bad = self.ping_sorted()
            tested = {r for r, _ in ok + bad}
            pending = [(r, None) for r in GAMES[self.game_var.get()] if r not in tested]
            for i, (r, v) in enumerate(ok + bad + pending):
                best = i == 0 and v is not None and v["avg"] is not None
                row = ctk.CTkFrame(fr, fg_color="transparent")
                row.pack(fill="x", pady=3)
                name, cc = REGIONS[r]
                self.label(row, f"{name}  ({cc})", 12, True, th["ok"] if best else th["text"], width=190, anchor="w").pack(side="left")
                if v is None:
                    txt = "—"
                elif v["avg"] is None:
                    txt = "НЕДОСТУПЕН"
                else:
                    txt = f"{round(v['avg'])} ms   ·   джиттер {round(v['jitter'])}   ·   потери {v['loss']}%"
                self.label(row, txt, 11, False, th["muted"], width=300, anchor="w").pack(side="left")
                bar = ctk.CTkProgressBar(row, width=160, height=8, fg_color=th["card2"], progress_color=th["ok"] if best else th["accent"])
                bar.pack(side="right")
                bar.set(0 if (v is None or v["avg"] is None) else max(0.04, min(1.0, 1 - v["avg"] / 300)))

        def ping_toggle(self):
            P = self.ping
            if P["running"]:
                P["stop"].set()
                self.ping_set_status("ОСТАНОВКА…")
                return
            P["running"] = True
            P["stop"] = threading.Event()
            P["results"], P["steps"], P["best"] = {}, [1, 0, 0, 0], None
            self.ping_set_status("ИДЁТ ПРОВЕРКА")
            if self.alive(self.ping_btn):
                self.ping_btn.configure(text="ОСТАНОВИТЬ", fg_color=self.th["bad"], hover_color=mix(self.th["bad"], "#000000", 0.18), text_color="#ffffff")
            self.ping_refresh()
            threading.Thread(target=self._ping_worker, args=(self.game_var.get(), P["stop"]), daemon=True).start()

        def _ping_worker(self, game, stop):
            P = self.ping
            ui = lambda fn, *a: self.q.put(functools.partial(fn, *a))
            base = tcp_ping("1.1.1.1", 443, 3, 1.5, stop)
            if stop.is_set():
                ui(self._ping_finish, "ОСТАНОВЛЕНО")
                return
            if base["avg"] is None:
                P["steps"] = [-1, 0, 0, 0]
                ui(self._ping_finish, "НЕТ ИНТЕРНЕТА")
                return
            P["steps"] = [2, 1, 0, 0]
            ui(self.ping_refresh)
            for r in GAMES[game]:
                if stop.is_set():
                    break
                P["results"][r] = tcp_ping(f"ec2.{r}.amazonaws.com", 443, 5, 1.5, stop)
                ui(self.ping_refresh)
            if stop.is_set():
                ui(self._ping_finish, "ОСТАНОВЛЕНО")
                return
            ok, _ = self.ping_sorted()
            if not ok:
                P["steps"] = [2, -1, 0, 0]
                ui(self._ping_finish, "УЗЛЫ НЕДОСТУПНЫ")
                return
            P["steps"] = [2, 2, 1, 0]
            ui(self.ping_refresh)
            best_r, best_v = ok[0]
            P["best"] = best_r
            P["steps"] = [2, 2, 2, 2]
            quality = "ОТЛИЧНАЯ" if best_v["loss"] == 0 and best_v["jitter"] < 10 else "СРЕДНЯЯ" if best_v["loss"] < 20 else "НЕСТАБИЛЬНАЯ"
            self.log(f"Лучший узел: {REGIONS[best_r][0]} — {round(best_v['avg'])} мс, джиттер {round(best_v['jitter'])}, потери {best_v['loss']}%. Связь: {quality}.")
            ui(self._ping_finish, f"ЛУЧШИЙ: {REGIONS[best_r][0]} · {round(best_v['avg'])} MS")

        def _ping_finish(self, text):
            P = self.ping
            P["running"] = False
            self.ping_set_status(text)
            if self.alive(getattr(self, "ping_btn", None)) and self.page == "ping":
                self.ping_btn.configure(text="ЗАПУСТИТЬ ПРОВЕРКУ", fg_color=self.th["accent"], hover_color=self.th["accent_h"], text_color=self.th["on_accent"])
            self.ping_refresh()

        # ---------- DNS ----------
        def dns_render(self):
            fr = getattr(self, "dns_frame", None)
            if not self.alive(fr):
                return
            th = self.th
            for w in fr.winfo_children():
                w.destroy()
            res = self.ping["dns"]
            valid = {k: v for k, v in res.items() if v is not None}
            best = min(valid, key=valid.get) if valid else None
            for name, p, s in DNS_SERVERS:
                row = ctk.CTkFrame(fr, fg_color="transparent")
                row.pack(fill="x", pady=2)
                self.label(row, name, 12, True, th["ok"] if name == best else th["text"], width=120, anchor="w").pack(side="left")
                self.label(row, f"{p} / {s}", 11, False, th["muted"], width=240, anchor="w").pack(side="left")
                v = res.get(name, "—")
                txt = "—" if v == "—" else "НЕТ ОТВЕТА" if v is None else f"{round(v)} ms"
                self.label(row, txt, 12, True, th["ok"] if name == best else th["muted"], anchor="w").pack(side="left")

        def dns_test_click(self):
            self.log("Проверяю скорость DNS-серверов…")

            def w():
                for name, p, s in DNS_SERVERS:
                    self.ping["dns"][name] = dns_ping(p)
                    self.q.put(self.dns_render)
                valid = {k: v for k, v in self.ping["dns"].items() if v is not None}
                self.log("Самый быстрый DNS: " + (min(valid, key=valid.get) if valid else "не найден"))
            threading.Thread(target=w, daemon=True).start()

        def dns_apply_click(self):
            valid = {k: v for k, v in self.ping["dns"].items() if v is not None}
            if not valid:
                self.log("Сначала нажмите «Проверить DNS».")
                return
            best = min(valid, key=valid.get)
            p, s = next((a, b) for n, a, b in DNS_SERVERS if n == best)

            def w():
                code, out = set_dns(p, s)
                if code == 0:
                    self.st["dns"] = best
                    save_state(self.st)
                self.log(f"DNS {best} ({p}) применён." if code == 0 else "Не удалось сменить DNS: " + out.strip()[:120])
            threading.Thread(target=w, daemon=True).start()

        def dns_reset_click(self):
            def w():
                code, out = reset_dns()
                if code == 0:
                    self.st.pop("dns", None)
                    save_state(self.st)
                self.log("DNS сброшен на автоматический." if code == 0 else "Не удалось сбросить DNS: " + out.strip()[:120])
            threading.Thread(target=w, daemon=True).start()

        # ---------- внешний вид ----------
        def set_ui(self, **kw):
            self.ui.update(kw)
            save_ui(self.ui)
            self.restyle()

        def restyle(self):
            self.th = build_theme(self.ui)
            ctk.set_appearance_mode("dark" if self.th["dark"] else "light")
            try:
                self.attributes("-alpha", float(self.ui["alpha"]))
            except Exception:
                pass
            self.opt_vars = {}
            self._build()
            self.show(self.page)

        def page_look(self):
            th = self.th
            sf = self.scroll(self.body)

            def section(title):
                c = self.card(sf)
                c.pack(fill="x", pady=(0, 12), padx=(0, 6))
                self.label(c, title, 11, True, th["muted"], anchor="w").pack(fill="x", padx=18, pady=(14, 8))
                inner = ctk.CTkFrame(c, fg_color="transparent")
                inner.pack(fill="x", padx=14, pady=(0, 14))
                return inner

            inner = section("ТЕМА")
            for i, name in enumerate(PRESETS):
                inner.grid_columnconfigure(i % 3, weight=1, uniform="p")
                cur = name == self.ui["preset"]
                ctk.CTkButton(inner, text=name.upper(), height=40, corner_radius=self.R, font=self.F(12, True),
                              fg_color=th["line"] if cur else th["card2"], hover_color=th["line"], text_color=th["text"],
                              border_width=2, border_color=PRESETS[name][1],
                              command=lambda n=name: self.set_ui(preset=n, accent=None)).grid(row=i // 3, column=i % 3, sticky="ew", padx=4, pady=4)

            inner = section("АКЦЕНТНЫЙ ЦВЕТ")
            sw = ctk.CTkFrame(inner, fg_color="transparent")
            sw.pack(fill="x")
            for col in ACCENTS:
                cur = self.th["accent"].lower() == col.lower()
                ctk.CTkButton(sw, text="", width=38, height=38, corner_radius=self.R, fg_color=col, hover_color=col,
                              border_width=3 if cur else 0, border_color=th["text"],
                              command=lambda c=col: self.set_ui(accent=c)).pack(side="left", padx=4, pady=4)
            hr = ctk.CTkFrame(inner, fg_color="transparent")
            hr.pack(fill="x", pady=(8, 0))
            hexv = tk.StringVar(value=self.th["accent"])
            self.opt_vars["hex"] = hexv
            ctk.CTkEntry(hr, textvariable=hexv, width=140, height=36, fg_color=th["card2"], border_color=th["line"],
                         text_color=th["text"], corner_radius=self.R, placeholder_text="#34E0A1").pack(side="left", padx=4)

            def apply_hex():
                v = hexv.get().strip()
                if valid_hex(v):
                    self.set_ui(accent=v)
                else:
                    self.log("Введите цвет в формате #RRGGBB, например #34E0A1.")
            self.btn(hr, "ПРИМЕНИТЬ HEX", apply_hex, "ghost", width=150, height=36).pack(side="left", padx=4)

            inner = section("РАЗМЕР ТЕКСТА И ЗАКРУГЛЕНИЕ")
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(fill="x")
            cur_s = next((k for k, v in SCALE_OPTS.items() if abs(v - float(self.ui["scale"])) < 0.01), "Обычный")
            cur_r = next((k for k, v in RAD_OPTS.items() if v == int(self.ui["radius"])), "Средние")
            for lab, vals, cur, cb in [("Текст", list(SCALE_OPTS), cur_s, lambda v: self.set_ui(scale=SCALE_OPTS[v])),
                                       ("Углы", list(RAD_OPTS), cur_r, lambda v: self.set_ui(radius=RAD_OPTS[v]))]:
                self.label(row, lab, 12, False, th["muted"]).pack(side="left", padx=(4, 8))
                ctk.CTkOptionMenu(row, values=vals, width=150, height=36, fg_color=th["card2"], button_color=th["line"],
                                  button_hover_color=th["muted"], text_color=th["text"], dropdown_fg_color=th["card"],
                                  dropdown_text_color=th["text"], dropdown_hover_color=th["card2"], corner_radius=self.R,
                                  command=cb).pack(side="left", padx=(0, 18))
                row.winfo_children()[-1].set(cur)

            inner = section("ОКНО И СПИСОК")
            ar = ctk.CTkFrame(inner, fg_color="transparent")
            ar.pack(fill="x", pady=(0, 8))
            self.label(ar, "Прозрачность окна", 12, False, th["muted"]).pack(side="left", padx=(4, 12))

            def on_alpha(v):
                v = round(float(v), 2)
                self.ui["alpha"] = v
                try:
                    self.attributes("-alpha", v)
                except Exception:
                    pass
            sl = ctk.CTkSlider(ar, from_=0.7, to=1.0, number_of_steps=15, width=260, command=on_alpha,
                               progress_color=th["accent"], button_color=th["accent"], button_hover_color=th["accent_h"], fg_color=th["line"])
            sl.set(float(self.ui["alpha"]))
            sl.pack(side="left")
            sl.bind("<ButtonRelease-1>", lambda _e: save_ui(self.ui))
            for key, text in [("desc", "Показывать описания твиков"), ("compact", "Компактные карточки")]:
                v = tk.IntVar(value=1 if self.ui[key] else 0)
                self.opt_vars[key] = v
                ctk.CTkSwitch(inner, text=text, variable=v, font=self.F(12), text_color=th["text"], progress_color=th["accent"],
                              fg_color=th["line"], button_color="#ffffff", button_hover_color="#e6e6e6",
                              command=lambda k=key, vv=v: self.set_ui(**{k: bool(vv.get())})).pack(anchor="w", padx=4, pady=6)
            self.btn(sf, "СБРОСИТЬ ВНЕШНИЙ ВИД", lambda: (self.ui.update(DEFAULT_UI), save_ui(self.ui), self.restyle()), "ghost", width=240, height=40).pack(anchor="w", pady=(0, 10))

    App().mainloop()


def main():
    if "--make-icon" in sys.argv:
        write_ico("W.ico")
        print("W.ico создан")
        return
    if os.name != "nt" or winreg is None:
        print("Wexxyy Tweaker работает только в Windows.")
        return
    if not is_admin():
        relaunch_as_admin()
        return
    launch_ui()


if __name__ == "__main__":
    main()
