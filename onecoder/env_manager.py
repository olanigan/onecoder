import os
import json
from pathlib import Path
from typing import Optional, Dict, List

class EnvManager:
    """Simplified local environment variable manager."""
    def __init__(self):
        self.config_dir = Path.home() / ".onecoder"
        self.secrets_file = self.config_dir / "secrets.json"
        self._ensure_config_dir()
        self._secrets_cache: Dict[str, str] = {}

    def _ensure_config_dir(self):
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.config_dir, 0o700)

    def set_env(self, key: str, value: str, project_path: Optional[str] = None):
        """Store an environment variable."""
        store_key = f"{key}@{project_path}" if project_path else key
        secrets = self._load_secrets()
        secrets[store_key] = value
        self._save_secrets(secrets)
        self._secrets_cache[store_key] = value

    def get_env(self, key: str, project_path: Optional[str] = None) -> Optional[str]:
        """Retrieve an environment variable."""
        store_key = f"{key}@{project_path}" if project_path else key
        if store_key in self._secrets_cache:
            return self._secrets_cache[store_key]
        secrets = self._load_secrets()
        value = secrets.get(store_key)
        if value:
            self._secrets_cache[store_key] = value
        return value

    def delete_env(self, key: str, project_path: Optional[str] = None):
        """Delete a stored environment variable."""
        store_key = f"{key}@{project_path}" if project_path else key
        secrets = self._load_secrets()
        if store_key in secrets:
            del secrets[store_key]
            self._save_secrets(secrets)
        if store_key in self._secrets_cache:
            del self._secrets_cache[store_key]

    def list_keys(self, project_path: Optional[str] = None) -> List[str]:
        """List keys available for a given project path."""
        all_secrets = self._load_secrets()
        keys = []
        for sk in all_secrets.keys():
            if "@" in sk:
                k, p = sk.rsplit("@", 1)
                if p == project_path:
                    keys.append(k)
            elif project_path is None:
                keys.append(sk)
        return list(set(keys))

    def _load_secrets(self) -> Dict[str, str]:
        if not self.secrets_file.exists():
            return {}
        try:
            with open(self.secrets_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_secrets(self, secrets: Dict[str, str]):
        with open(self.secrets_file, "w") as f:
            json.dump(secrets, f, indent=4)
        os.chmod(self.secrets_file, 0o600)

    def redact(self, text: str) -> str:
        """Simplified redaction."""
        secrets = self._load_secrets()
        for val in secrets.values():
            if len(val) > 4:
                text = text.replace(val, "[REDACTED]")
        return text

env_manager = EnvManager()