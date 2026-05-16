import json
import os
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.json"


class Config:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        with open(config_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    @property
    def base_url(self) -> str:
        return self._data["base_url"]

    @property
    def request_delay(self) -> dict:
        return self._data["request_delay"]

    @property
    def max_retries(self) -> int:
        return self._data["max_retries"]

    @property
    def timeout(self) -> int:
        return self._data["timeout"]

    @property
    def user_agent(self) -> str:
        return self._data["user_agent"]

    @property
    def subjects(self) -> dict:
        return self._data["subjects"]

    @property
    def grade_levels(self) -> dict:
        return self._data["grade_levels"]

    @property
    def question_types(self) -> dict:
        return self._data["question_types"]

    @property
    def difficulty_levels(self) -> dict:
        return self._data["difficulty_levels"]

    @property
    def output_dir(self) -> Path:
        rel = self._data["output"]["dir"]
        return CONFIG_DIR / rel

    @property
    def max_screenshot_size_mb(self) -> int:
        return self._data["output"]["max_screenshot_size_mb"]

    def subject_path(self, subject: str, level: str) -> str:
        return self._data["subjects"][subject][level]

    def get(self, key: str, default=None):
        keys = key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
