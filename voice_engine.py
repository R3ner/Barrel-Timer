import json
import os
import pyaudio
import time
from PySide6.QtCore import QThread, Signal
from vosk import Model, KaldiRecognizer

class VoiceEngine(QThread):
    command_detected = Signal(str, str)  # (role, spell)
    status_updated = Signal(str)
    text_detected = Signal(str) # For the live preview

    def __init__(self, model_path, mic_index=None):
        super().__init__()
        self.model_path = model_path
        self.mic_index = mic_index
        self.muted = False
        self.running = True
        # Define roles and spells for grammar
        self.roles = {
            "top": "top",
            "stop": "top", 
            "jungle": "jungler",
            "young": "jungler",  
            "uncle": "jungler",  
            "mid": "mid",
            "meet": "mid",   
            "meat": "mid",
            "adc": "adc",
            "eighty": "adc", 
            "abc": "adc",    
            "ades": "adc",   
            "carry": "adc",
            "support": "support",
            "supp": "support",
            "sport": "support",
            "port": "support",
        }
        
        self.spells = {
            "flash": "flash",
            "flas": "flash",
            "flesh": "flash",
            "flush": "flash", 
            "ignite": "ignite",
            "night": "ignite",  
            "unite": "ignite", 
            "teleport": "teleport",
            "tepe": "teleport",
            "tp": "teleport",
            "tv": "teleport",   
            "ghost": "ghost",
            "gos": "ghost",
            "goes": "ghost",   
            "gold": "ghost",   
            "barrier": "barrier",
            "barr": "barrier",
            "cleanse": "cleanse",
            "cleans": "cleanse",
            "clean": "cleanse",
            "exhaust": "exhaust",
            "exos": "exhaust",
            "smite": "smite",
            "might": "smite",  
            "smile": "smite",  
            "heal": "heal",
            "jil": "heal",
            "hill": "heal",   
            "hell": "heal",   
            "ill": "heal",
            "start": "start",
            "game": "game",
            "timer": "timer"
        }

        grammar_list = list(self.roles.keys()) + list(self.spells.keys())
        self.grammar = json.dumps(grammar_list)


    def set_microphone(self, index):
        self.mic_index = index

    def set_muted(self, muted):
        self.muted = muted

    def run(self):
        if not os.path.exists(self.model_path):
            self.status_updated.emit(f"Model not found at {self.model_path}")
            return

        try:
            model = Model(self.model_path)
            p = pyaudio.PyAudio()
            
            # Function to start stream
            def start_stream(index):
                return p.open(format=pyaudio.paInt16, channels=1, rate=16000, 
                             input=True, frames_per_buffer=8000, input_device_index=index)

            rec = KaldiRecognizer(model, 16000, self.grammar)
            stream = start_stream(self.mic_index)
            stream.start_stream()

            self.status_updated.emit("Voice recognition active")
            current_mic = self.mic_index

            while self.running:
                # Check if mic changed
                if current_mic != self.mic_index:
                    stream.stop_stream()
                    stream.close()
                    stream = start_stream(self.mic_index)
                    stream.start_stream()
                    current_mic = self.mic_index

                if self.muted:
                    time.sleep(0.1)
                    continue

                data = stream.read(4000, exception_on_overflow=False)
                if len(data) == 0:
                    break
                
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "")
                    if text:
                        self.text_detected.emit(text)
                        self.process_text(text)
            
            stream.stop_stream()
            stream.close()
            p.terminate()

        except Exception as e:
            self.status_updated.emit(f"Error in voice engine: {str(e)}")

    def process_text(self, text):
        try:
            words = text.split()
            detected_role = None
            detected_spell = None

            for word in words:
                if word in self.roles:
                    detected_role = self.roles[word]
                elif word in self.spells:
                    detected_spell = self.spells[word]

            if detected_role and detected_spell:
                interpretation = f"{detected_role.upper()} {detected_spell.upper()}"
                self.text_detected.emit(f"Vosk: \"{text}\" -> Timer: {interpretation}")
                self.command_detected.emit(detected_role, detected_spell)
            elif "start" in words and ("game" in words or "timer" in words):
                 self.text_detected.emit(f"Vosk: \"{text}\" -> Game Start Command")
                 self.command_detected.emit("game", "start")
            else:
                self.text_detected.emit(f"Vosk: \"{text}\" (No interpretation)")

        except Exception as e:
            print(f"Error in process_text: {e}")

    def stop(self):
        self.running = False
        self.wait()
