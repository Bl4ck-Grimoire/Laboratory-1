"""
log.py

Minimal logging utility for the ETL pipeline.

Follows the same idea as the reference pipeline (timestamp + message
appended to a plain text file), with two small fixes so it works
correctly in this project:

    1. The log file's parent directory is created automatically if it
       does not exist yet (the reference version assumed the folder
       was already there).
    2. A `level` argument (INFO / WARNING / ERROR) is included so the
       log can distinguish normal progress messages from problems,
       which main.py needs when it has to decide whether to stop the
       pipeline.
"""

import os
import datetime


def log_progress(message, log_file, level="INFO"):
    """
    Append a timestamped line to the log file.

    Parameters
    ----------
    message : str
        Message to record.
    log_file : str
        Path to the log file (e.g. logs/log_file.txt).
    level : str
        One of "INFO", "WARNING", "ERROR". Defaults to "INFO".
    """
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
