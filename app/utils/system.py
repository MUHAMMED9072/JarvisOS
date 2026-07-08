import psutil
import platform
import socket
import datetime


def cpu_usage():
    return f"{psutil.cpu_percent(interval=0.2)} %"


def ram_usage():
    ram = psutil.virtual_memory()
    return f"{ram.percent} %"


def disk_usage():
    disk = psutil.disk_usage("/")
    return f"{disk.percent} %"


def current_time():
    return datetime.datetime.now().strftime("%I:%M:%S %p")


def python_version():
    return platform.python_version()


def operating_system():
    return platform.system() + " " + platform.release()


def internet_status():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return "Connected"
    except:
        return "Offline"