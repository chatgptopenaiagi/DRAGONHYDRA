import time
import threading


class RateLimiter:
    def __init__(self):
        self.last = {}
        self.lock = threading.Lock()

    def wait(self, host, interval):
        with self.lock:
            delay = interval - (time.monotonic() - self.last.get(host, -1e10))
            if delay > 0:
                time.sleep(delay)
            self.last[host] = time.monotonic()


LIMITER = RateLimiter()
