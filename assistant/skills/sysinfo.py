"""
System Info Skill — Battery, RAM, Storage, WiFi, CPU.
"""

import logging
import platform
import subprocess
from typing import Dict

import psutil

logger = logging.getLogger(__name__)


def get_battery() -> Dict[str, str]:
    """Get battery percentage and charging status."""
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return {"status": "success", "message": "Battery nahi mili — desktop PC lag raha hai."}

        percent = battery.percent
        plugged = "charging" if battery.power_plugged else "not charging"
        time_left = ""
        if battery.secsleft > 0 and not battery.power_plugged:
            mins = battery.secsleft // 60
            hrs = mins // 60
            mins = mins % 60
            time_left = f", {hrs}h {mins}m baaki"

        msg = f"Battery {percent}% hai ({plugged}){time_left}."
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_ram_usage() -> Dict[str, str]:
    """Get RAM usage info."""
    try:
        ram = psutil.virtual_memory()
        total_gb = ram.total / (1024 ** 3)
        used_gb = ram.used / (1024 ** 3)
        percent = ram.percent

        msg = f"RAM: {used_gb:.1f}GB / {total_gb:.1f}GB use ho rahi hai ({percent}%)."
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_storage() -> Dict[str, str]:
    """Get disk storage info."""
    try:
        partitions = psutil.disk_partitions()
        info_parts = []
        for p in partitions:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                total_gb = usage.total / (1024 ** 3)
                free_gb = usage.free / (1024 ** 3)
                percent = usage.percent
                info_parts.append(f"{p.device} — {free_gb:.0f}GB free / {total_gb:.0f}GB ({percent}% used)")
            except PermissionError:
                continue

        msg = "Storage:\n" + "\n".join(info_parts)
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_cpu_usage() -> Dict[str, str]:
    """Get CPU usage."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        msg = f"CPU {cpu_percent}% use ho raha hai ({cpu_count} cores)."
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_wifi_status() -> Dict[str, str]:
    """Get WiFi connection status and network name."""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout
            ssid = ""
            signal = ""
            for line in output.split("\n"):
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(":")[1].strip()
                if "Signal" in line:
                    signal = line.split(":")[1].strip()

            if ssid:
                msg = f"WiFi connected: '{ssid}' (Signal: {signal})."
            else:
                msg = "WiFi disconnected hai."
            return {"status": "success", "message": msg}
        else:
            return {"status": "success", "message": "WiFi check Linux pe available nahi."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_system_info() -> Dict[str, str]:
    """Get complete system overview."""
    try:
        parts = []

        # Battery
        battery = psutil.sensors_battery()
        if battery:
            plug = "⚡" if battery.power_plugged else "🔋"
            parts.append(f"{plug} Battery: {battery.percent}%")

        # RAM
        ram = psutil.virtual_memory()
        parts.append(f"💾 RAM: {ram.percent}% used ({ram.used/(1024**3):.1f}/{ram.total/(1024**3):.1f}GB)")

        # CPU
        cpu = psutil.cpu_percent(interval=0.5)
        parts.append(f"🖥️ CPU: {cpu}%")

        # Storage (C drive)
        try:
            disk = psutil.disk_usage("C:\\")
            parts.append(f"💿 C: {disk.free/(1024**3):.0f}GB free / {disk.total/(1024**3):.0f}GB")
        except Exception:
            pass

        msg = "\n".join(parts)
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}
