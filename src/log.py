import os
import datetime


def log_progress(message, log_file, level="INFO"):
    
    #Append a timestamped line to the log file.

    timestamp_format = '%Y-%m-%d %H:%M:%S'
    now = datetime.datetime.now()
    timestamp = now.strftime(timestamp_format)

    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp},{level},{message}\n")

    # Mirror to console so progress is visible while running main.py
    print(f"[{timestamp}] [{level}] {message}")
