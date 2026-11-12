"""Utilidades sin dependencias del resto: RAM, fechas, escritura atomica, formato de tiempo, notificaciones."""
import ctypes, datetime, os, sys
from pathlib import Path


def _pmc_windows():
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = ctypes.c_void_p            # HANDLE de 64 bits (sin esto se trunca)
    k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
    k32.K32GetProcessMemoryInfo.restype = ctypes.c_int
    if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        raise OSError("GetProcessMemoryInfo fallo")
    return pmc


def ram_mb():
    """RSS actual del proceso en MB (None si no se puede medir)."""
    try:
        if os.name == "nt":
            return _pmc_windows().WorkingSetSize / 1048576
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1048576
    except Exception:
        return None


def ram_pico_mb():
    """Pico de RSS del propio proceso en MB."""
    try:
        if os.name == "nt":
            return _pmc_windows().PeakWorkingSetSize / 1048576
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmHWM:"):
                        return int(line.split()[1]) / 1024
        except OSError:
            pass
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r / (1048576 if sys.platform == "darwin" else 1024)
    except Exception:
        return None


def ahora():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def escritura_atomica(path: Path, texto: str):
    """tmp + fsync + replace: el archivo final nunca queda a medias."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def fmt_t(s):
    if s != s or s == float("inf"):
        return "--"
    s = int(s)
    d, s = divmod(s, 86400); h, s = divmod(s, 3600); m, s = divmod(s, 60)
    return (f"{d}d " if d else "") + f"{h:02d}:{m:02d}:{s:02d}"


def notificar(titulo: str, mensaje: str):
    """Aviso del sistema (sonido + notificacion de escritorio si el SO lo permite). Nunca lanza errores."""
    import shutil, subprocess
    titulo = titulo.replace("'", "’").replace('"', "”")
    mensaje = mensaje.replace("'", "’").replace('"', "”")
    try:
        if os.name == "nt":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            ps = ("Add-Type -AssemblyName System.Windows.Forms;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;"
                  "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
                  f"$n.ShowBalloonTip(10000,'{titulo}','{mensaje}',[System.Windows.Forms.ToolTipIcon]::Info);"
                  "Start-Sleep -Seconds 11;$n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                             creationflags=0x08000000)
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", f'display notification "{mensaje}" with title "{titulo}"'])
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", titulo, mensaje])
    except Exception:
        pass
