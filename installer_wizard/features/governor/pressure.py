def score(cpu: float, mem: float, swap: float, load_per_core: float) -> float:
    parts = (cpu, load_per_core * 90.0, max(0.0, mem - 50.0) * 2.0, swap * 1.5)
    return max(0.0, min(100.0, max(parts)))


class Pressure:

    def __init__(self, alpha: float = 0.4) -> None:
        self.alpha = alpha
        self.value = 0.0
        self.high = False
        self.since = 0.0

    def update(self, raw: float, enter: float, leave: float, now: float) -> float:
        self.value = raw if not self.value else self.value + (raw - self.value) * self.alpha
        was = self.high
        if self.value >= enter:
            self.high = True
        elif self.value <= min(leave, enter):
            self.high = False
        if self.high != was:
            self.since = now
        return self.value
