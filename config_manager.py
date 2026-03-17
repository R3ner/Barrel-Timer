# Barrel Timer v1.9.4-a - Developed by Rener
import json
import os

class ConfigManager:
    DEFAULT_CONFIG = {
        "voice_set": "v2",  # v1 or v2
        "volume": 0.8,
        "language": "en-us",
        "microphone_index": None,
        "debug_mode": False,
        "debug_duration": 5
    }
    CONFIG_PATH = "config.json"

    @staticmethod
    def load_config():
        if os.path.exists(ConfigManager.CONFIG_PATH):
            try:
                with open(ConfigManager.CONFIG_PATH, 'r') as f:
                    return {**ConfigManager.DEFAULT_CONFIG, **json.load(f)}
            except Exception as e:
                print(f"Error loading config: {e}")
        return ConfigManager.DEFAULT_CONFIG.copy()

    @staticmethod
    def save_config(config):
        try:
            with open(ConfigManager.CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    @staticmethod
    def get_voice_set_path(voice_set, base_assets_path="assets/sounds"):
        if voice_set == "v2":
            return os.path.join(base_assets_path, "v2")
        return base_assets_path
