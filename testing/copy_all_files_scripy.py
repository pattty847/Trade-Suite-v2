import os
import shutil


def copy_files(startpath, destpath):
    if not os.path.exists(destpath):
        os.makedirs(destpath)

    for root, dirs, files in os.walk(startpath, topdown=True):
        # Exclude specific directories
        dirs[:] = [
            d
            for d in dirs
            if d not in ["venv", "__pycache__", ".env", ".gitignore", ".git"]
        ]

        # Calculate the relative path from startpath to root
        relative_path = os.path.relpath(root, startpath)

        # Create corresponding directory in the destination folder
        dest_dir = os.path.join(destpath, relative_path)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        for f in files:
            # Copy each file to the corresponding directory in the destination folder
            shutil.copy2(os.path.join(root, f), os.path.join(dest_dir, f))


# Replace with the path to your project's main directory and the destination directory
copy_files(
    r"C:\Users\Pepe\Documents\Programming\Python\CVD Dash",
    r"C:\Users\Pepe\Documents\Programming\Python\CVD Dash Backup",
)
