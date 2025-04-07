"""
Build script to create a standalone executable for Trade-Suite-v2
This creates a single-file executable that users can double-click to run
"""

import os
import sys
import subprocess
import platform

def main():
    print("Building Trade-Suite-v2 standalone executable...")
    
    # Check if PyInstaller is installed, if not, install it
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing it now...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Create build directory if it doesn't exist
    if not os.path.exists("dist"):
        os.makedirs("dist")
    
    # Determine OS-specific settings
    icon_path = None
    if platform.system() == "Windows":
        icon_path = "resources/icon.ico"
    elif platform.system() == "Darwin":  # macOS
        icon_path = "resources/icon.icns"
    
    # Create resources directory and icon placeholder if they don't exist
    if icon_path and not os.path.exists(os.path.dirname(icon_path)):
        os.makedirs(os.path.dirname(icon_path))
    
    # Create a placeholder icon file if it doesn't exist
    if icon_path and not os.path.exists(icon_path):
        print(f"Note: No icon file found at {icon_path}. Using default icon.")
        icon_param = []
    else:
        icon_param = ["--icon", icon_path]
    
    # Build the PyInstaller command
    cmd = [
        "pyinstaller",
        "--onefile",
        "--windowed",
        "--name", "TradeSuite",
        "--clean",
        *icon_param,
        "--add-data", ".env.template;." if platform.system() == "Windows" else ".env.template:.",
        "--add-data", "config.json;." if platform.system() == "Windows" else "config.json:.",
        "main.py"
    ]
    
    # Run PyInstaller
    try:
        subprocess.run(cmd, check=True)
        print("\nBuild successful! Executable created in the 'dist' folder.")
        print("Users can now run the application by double-clicking the executable.")
    except subprocess.CalledProcessError as e:
        print(f"Error building executable: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: PyInstaller not found. Please install it with 'pip install pyinstaller'")
        sys.exit(1)
    
    # Create a README file with instructions
    with open("dist/README.txt", "w") as f:
        f.write("""
TradeSuite - Cryptocurrency Trading Dashboard
=============================================

To run the application:
1. Double-click the 'TradeSuite' executable file
2. The application will start with public access to cryptocurrency data
3. No configuration is required for basic usage

For advanced features:
1. Create a file named '.env' in the same folder as the executable
2. Use the '.env.template' file as a guide to add your API keys
3. Restart the application

Enjoy using TradeSuite!
""")
    
    print("Added README.txt with usage instructions")

if __name__ == "__main__":
    main() 