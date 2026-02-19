import json
import logging
import os
import shutil # Added shutil import
from typing import Any, Dict, List  # Added typing imports

import dearpygui.dearpygui as dpg  # Added dpg import


class ConfigManager:
    _instance = None

    def __new__(cls, config_dir: str = "config"):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            # Store config_dir and filenames
            cls.config_dir = config_dir
            cls.user_layout_ini = "user_layout.ini"
            cls.factory_layout_ini = "factory_layout.ini"
            cls.user_widgets_json = "user_widgets.json"
            cls.factory_widgets_json = "factory_widgets.json" # Derived filename
            cls.config_json_file = "config.json" # Existing config file

            # Ensure directory exists
            cls.ensure_config_directories()

            # Existing config.json handling
            cls._config_file = os.path.join(cls.config_dir, cls.config_json_file)
            cls._default_config = {"default_exchange": "coinbase"}
            cls._config = cls.load_config() # Load existing config
        return cls._instance

    @classmethod
    def ensure_config_directories(cls):
        """Creates the configuration directory if it doesn't exist."""
        try:
            os.makedirs(cls.config_dir, exist_ok=True)
            logging.debug(f"Ensured config directory exists: {cls.config_dir}")
        except OSError as e:
            logging.error(f"Error creating config directory {cls.config_dir}: {e}")
            # Depending on the application, might want to raise or exit here

    # --- Path Methods ---

    def get_user_layout_ini_path(self) -> str:
        """Returns the absolute path to the user's layout INI file."""
        return os.path.abspath(os.path.join(self.config_dir, self.user_layout_ini))

    def get_factory_layout_ini_path(self) -> str:
        """Returns the absolute path to the factory default layout INI file."""
        return os.path.abspath(os.path.join(self.config_dir, self.factory_layout_ini))

    def get_user_widgets_json_path(self) -> str:
        """Returns the absolute path to the user's widget configuration JSON file."""
        return os.path.abspath(os.path.join(self.config_dir, self.user_widgets_json))

    def get_default_widgets_json_path(self) -> str:
        """Returns the absolute path to the default widget configuration JSON file."""
        # We'll derive this name, perhaps from the factory INI name or keep it simple
        return os.path.abspath(os.path.join(self.config_dir, self.factory_widgets_json))


    # --- File I/O Methods ---

    def save_dpg_layout(self, is_default: bool = False):
        """Saves the current Dear PyGui layout to the appropriate INI file."""
        target_path = self.get_factory_layout_ini_path() if is_default else self.get_user_layout_ini_path()
        try:
            dpg.save_init_file(target_path)
            logging.info(f"Dear PyGui layout saved to: {target_path}")
        except Exception as e: # Catching general Exception as dpg doesn't specify errors
            logging.error(f"Error saving Dear PyGui layout to {target_path}: {e}")

    def load_widget_config(self) -> List[Dict[str, Any]]:
        """Loads widget configuration from user JSON, falling back to factory defaults.

        If the user configuration file doesn't exist, it attempts to load the
        factory default configuration. If the factory default exists and is loaded
        successfully, it's copied to the user configuration path for future use.

        Returns:
            List[Dict[str, Any]]: A list of widget definition dictionaries.
                                  Returns an empty list if neither user nor factory
                                  config exists or if loading fails.
        """
        user_path = self.get_user_widgets_json_path()
        factory_path = self.get_default_widgets_json_path()
        config_to_load = None
        loaded_from = None

        if os.path.exists(user_path):
            config_to_load = user_path
            loaded_from = "user"
            logging.info(f"Found user widget config: {user_path}")
        elif os.path.exists(factory_path):
            config_to_load = factory_path
            loaded_from = "factory"
            logging.info(f"User widget config not found. Found factory default: {factory_path}")
        else:
            logging.warning(f"Neither user ({user_path}) nor factory ({factory_path}) widget config file found. Returning empty list.")
            return []

        try:
            with open(config_to_load, 'r', encoding='utf-8') as f:
                widget_data = json.load(f)
                if not isinstance(widget_data, list):
                    logging.error(f"Invalid format in widget config file {config_to_load}. Expected a list.")
                    return []

                logging.info(f"Loaded {len(widget_data)} widget definitions from {loaded_from} config: {config_to_load}.")

                # If loaded from factory, copy it to user path
                if loaded_from == "factory":
                    try:
                        shutil.copy2(factory_path, user_path) # copy2 preserves metadata
                        logging.info(f"Copied factory widget config to user path: {user_path}")
                    except Exception as copy_e:
                        logging.error(f"Error copying factory widget config {factory_path} to {user_path}: {copy_e}")
                        # Proceed with loaded data even if copy fails, but log the error

                return widget_data
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from {config_to_load}: {e}")
            return []
        except IOError as e:
            logging.error(f"Error reading widget config file {config_to_load}: {e}")
            return []

    def save_widget_config(self, widget_data: List[Dict[str, Any]], is_default: bool = False):
        """Saves the widget configuration list to the appropriate JSON file."""
        target_path = self.get_default_widgets_json_path() if is_default else self.get_user_widgets_json_path()
        try:
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(widget_data, f, indent=4) # Use indent for readability
            logging.info(f"Saved {len(widget_data)} widget definitions to: {target_path}")
        except TypeError as e:
            logging.error(f"Error serializing widget data to JSON for {target_path}: {e}")
        except IOError as e:
            logging.error(f"Error writing widget config file {target_path}: {e}")

    def delete_user_layout(self):
        """Safely deletes the user layout INI file."""
        path = self.get_user_layout_ini_path()
        try:
            if os.path.exists(path):
                os.remove(path)
                logging.info(f"Deleted user layout file: {path}")
            else:
                logging.warning(f"Attempted to delete non-existent user layout file: {path}")
        except OSError as e:
            logging.error(f"Error deleting user layout file {path}: {e}")

    def delete_user_widget_config(self):
        """Safely deletes the user widget configuration JSON file."""
        path = self.get_user_widgets_json_path()
        try:
            if os.path.exists(path):
                os.remove(path)
                logging.info(f"Deleted user widget config file: {path}")
            else:
                logging.warning(f"Attempted to delete non-existent user widget config file: {path}")
        except OSError as e:
            logging.error(f"Error deleting user widget config file {path}: {e}")


    # --- Existing Config Methods ---
    @classmethod
    def load_config(cls):
        # Ensure config directory exists before trying to load/create config.json
        cls.ensure_config_directories() # Call ensure_config_directories here too

        if (
            not os.path.exists(cls._config_file)
            or os.path.getsize(cls._config_file) == 0
        ):
            # File does not exist or is empty. Initialize with default config.
            logging.info(f"Config file {cls._config_file} not found or empty. Creating with defaults.")
            try:
                with open(cls._config_file, "w", encoding="utf-8") as file:
                    json.dump(cls._default_config, file, indent=4) # Added indent
                return cls._default_config
            except IOError as e:
                 logging.error(f"Error creating default config file {cls._config_file}: {e}")
                 return cls._default_config # Return default even if write fails

        try:
            with open(cls._config_file, "r", encoding="utf-8") as file:
                config_data = json.load(file)
                logging.info(f"Loaded config from {cls._config_file}")
                return config_data
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from {cls._config_file}: {e}. Returning default config.")
            return cls._default_config # Return default if file is corrupt
        except IOError as e:
             logging.error(f"Error reading config file {cls._config_file}: {e}. Returning default config.")
             return cls._default_config # Return default if read fails


    def get_setting(self, key):
        return self._config.get(key, None)

    def update_setting(self, key, value):
        logging.info(f"Updating setting: '{key}' = '{value}'") # Improved logging
        self._config[key] = value
        try:
            with open(self._config_file, "w", encoding="utf-8") as file:
                json.dump(self._config, file, indent=4) # Added indent
            logging.info(f"Settings saved to {self._config_file}")
        except IOError as e:
            logging.error(f"Error writing settings to {self._config_file}: {e}")
        # logging.info("Done.") # Removed redundant "Done."
