GAIN = 2.5
MAX = 4.0
I_GAIN = 2.0
I_MAX = 2.0
STALE_DRIFT = 1.5
STALE_TIME = 1.0
class DepthHold:
    def __init__(self):
        self.reset()
    def reset(self):
        self.target = None
        self.i = 0.0
        self.stale_since = None
    def step(self, height, now, dt):
        if self.target is None:
            self.target, self.i = height, 0.0
        err = height - self.target
        stale = False
        if err > STALE_DRIFT and self.i - GAIN * err <= -MAX:
            self.stale_since = self.stale_since if self.stale_since is not None else now
            if now - self.stale_since > STALE_TIME:
                stale, self.stale_since = True, None
        else:
            self.stale_since = None
        self.i = max(-I_MAX, min(I_MAX, self.i - I_GAIN * err * dt))
        return max(-MAX, min(MAX, self.i - GAIN * err)), stale
