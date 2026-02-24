import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".onecoder"
        self.config_file = self.config_dir / "config.json"
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.config_dir, 0o700)

    def load_config(self) -> Dict[str, Any]:
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except Exception as e:
            return {}

    def save_config(self, config: Dict[str, Any]):
        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=4)
            os.chmod(self.config_file, 0o600)
        except Exception:
            pass

    def get_model_config(self) -> Optional[Dict[str, Any]]:
        config = self.load_config()
        return config.get("model")

    def set_model_config(self, model_config: Dict[str, Any]):
        config = self.load_config()
        config["model"] = model_config
        self.save_config(config)

config_manager = ConfigManager()