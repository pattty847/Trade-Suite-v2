import os
import sys

def copy_python_files_to_text(directory_path, output_file_path):
    """
    Recursively walks through a directory and copies all Python files into a single text document.
    Each file is preceded by its relative path as a header.
    
    Args:
        directory_path (str): Path to the directory to scan
        output_file_path (str): Path where the output text file will be created
    """
    # Convert to absolute path for consistency
    directory_path = os.path.abspath(directory_path)
    
    # Check if directory exists
    if not os.path.isdir(directory_path):
        print(f"Error: '{directory_path}' is not a valid directory")
        return False
    
    # Open output file for writing
    try:
        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            # Walk through directory
            for root, _, files in os.walk(directory_path):
                for file in files:
                    # Check if file is a Python file
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        # Calculate the relative path from the input directory
                        rel_path = os.path.relpath(file_path, directory_path)
                        
                        try:
                            # Read file content
                            with open(file_path, 'r', encoding='utf-8') as python_file:
                                content = python_file.read()
                            
                            # Write file path and content to output file
                            output_file.write(f"\n{'=' * 80}\n")
                            output_file.write(f"FILE: {rel_path}\n")
                            output_file.write(f"{'=' * 80}\n\n")
                            output_file.write(content)
                            output_file.write("\n\n")
                            
                            print(f"Added: {rel_path}")
                        except Exception as e:
                            print(f"Error reading {file_path}: {e}")
                            
        print(f"\nPython files have been copied to '{output_file_path}'")
        return True
    except Exception as e:
        print(f"Error writing to output file: {e}")
        return False

if __name__ == "__main__":
    # Check if command line arguments were provided
    if len(sys.argv) != 3:
        print("Usage: python copy_python_files.py <directory_path> <output_file_path>")
        sys.exit(1)
    
    directory_path = sys.argv[1]
    output_file_path = sys.argv[2]
    
    success = copy_python_files_to_text(directory_path, output_file_path)
    sys.exit(0 if success else 1) 