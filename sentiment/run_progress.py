"""Live progress for a manually started update; never schedules work."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime
import sys
import threading
import time

class Tee:
    def __init__(self, console, log, lock):
        self.console, self.log, self.lock = console, log, lock
    def write(self, text):
        with self.lock:
            self.console.write(text)
            self.log.write(text)
            self.log.flush()
        return len(text)
    def flush(self):
        with self.lock:
            self.console.flush()
            self.log.flush()

@contextmanager
def logged_run(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log:
        lock = threading.RLock()
        with redirect_stdout(Tee(sys.stdout, log, lock)), redirect_stderr(Tee(sys.stderr, log, lock)):
            yield

def say(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)

@contextmanager
def stage_progress(name, interval=10):
    started = time.monotonic()
    stopped = threading.Event()
    def report_wait():
        while not stopped.wait(interval):
            say(f"仍在运行：{name} · 本步骤已用 {time.monotonic() - started:.0f} 秒；正在采集或计算，尚未确认完成。")
    worker = threading.Thread(target=report_wait, daemon=True)
    say(f"开始：{name}")
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        worker.join()
