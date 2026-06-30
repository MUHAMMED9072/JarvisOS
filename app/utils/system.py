import psutil
from datetime import datetime


def get_system_info():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent

    return {
        "cpu": cpu,
        "ram": ram,
        "internet": "Connected",
        "voice": "Ready",
        "ollama": "Online",
        "time": datetime.now().strftime("%I:%M:%S %p"),
        "date": datetime.now().strftime("%A, %d %B %Y")
    }