# Barrel Timer v1.9.4-a - Developed by Rener
import time

class SpellTimer:
    BASE_COOLDOWNS = {
        "flash": 300,
        "ignite": 180,
        "teleport": 360,
        "ghost": 210,
        "barrier": 150,
        "cleanse": 210,
        "exhaust": 210,
        "smite": 90,
        "heal": 240
    }

    def __init__(self, spell_name, callback_tick=None, callback_finished=None):
        self.spell_name = spell_name.lower()
        self.base_cd = self.BASE_COOLDOWNS.get(self.spell_name, 300)
        self.remaining_time = 0
        self.is_running = False
        self.callback_tick = callback_tick
        self.callback_finished = callback_finished

    def start(self):
        self.remaining_time = self.base_cd
        self.is_running = True

    def tick(self):
        if self.is_running and self.remaining_time > 0:
            self.remaining_time -= 1
            if self.callback_tick:
                self.callback_tick(self.remaining_time)
            
            if self.remaining_time <= 0:
                self.is_running = False
                if self.callback_finished:
                    self.callback_finished()
        return self.remaining_time

    def get_remaining_str(self):
        if self.remaining_time <= 0:
            return "READY"
        mins = self.remaining_time // 60
        secs = self.remaining_time % 60
        return f"{mins}:{secs:02d}"
