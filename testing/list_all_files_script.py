import os


def list_files(startpath):
    for root, dirs, files in os.walk(startpath, topdown=True):
        # Exclude specific directories
        dirs[:] = [
            d
            for d in dirs
            if d not in ["venv", "__pycache__", ".env", ".gitignore", ".git"]
        ]

        level = root.replace(startpath, "").count(os.sep)
        indent = " " * 4 * (level)
        print(f"{indent}{os.path.basename(root)}/")
        subindent = " " * 4 * (level + 1)
        for f in files:
            print(f"{subindent}{f}")


# Replace with the path to your project's main directory
list_files(r"C:\Users\Pepe\Documents\Programming\Python\CVD Dash")
