import json
import os


class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._config_file = "config.json"
            cls._default_config = {"last_exchange": "coinbasepro"}
            cls._config = cls.load_config()
        return cls._instance

    @classmethod
    def load_config(cls):
        if (
            not os.path.exists(cls._config_file)
            or os.path.getsize(cls._config_file) == 0
        ):
            # File does not exist or is empty. Initialize with default config.
            with open(cls._config_file, "w") as file:
                json.dump(cls._default_config, file)
            return cls._default_config
        else:
            with open(cls._config_file, "r") as file:
                return json.load(file)

    def get_setting(self, key):
        return self._config.get(key, None)

    def update_setting(self, key, value):
        self._config[key] = value
        with open(self._config_file, "w") as file:
            json.dump(self._config, file)