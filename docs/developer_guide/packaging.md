# Packaging the Application

The original `README.md` contained detailed notes on distributing TradeSuite.
Those instructions are preserved here.

## Option 1: Creating a Standalone Executable

Building a self-contained executable is ideal for end users who do not want a
Python environment.

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Run the build script:
   ```bash
   # Windows
   python scripts/build/build_executable.py

   # macOS/Linux
   python3 scripts/build/build_executable.py
   ```
3. The resulting binary is placed in the `dist` directory.

## Option 2: Using UV for Package Management

UV is a modern alternative to pip that provides reproducible, fast installs.

1. Install UV:
   ```bash
   pip install uv
   ```
2. Install dependencies and maintain a lockfile:
   ```bash
   uv pip install -r requirements.txt
   uv pip compile --output-file requirements.lock requirements.txt
   uv pip install -r requirements.lock
   ```
3. Create and activate a virtual environment with UV:
   ```bash
   uv venv
   source .venv/bin/activate  # Linux/macOS
   .venv\Scripts\activate     # Windows
   ```
4. Export frozen dependencies if required:
   ```bash
   uv pip freeze > requirements-frozen.txt
   ```

Refer to the [UV documentation](https://github.com/astral-sh/uv) for more
details.
