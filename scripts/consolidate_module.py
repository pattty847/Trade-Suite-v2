import argparse
import pathlib
import tiktoken

def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Counts the number of tokens in a string using tiktoken."""
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        num_tokens = len(encoding.encode(text))
        return num_tokens
    except Exception as e:
        print(f"Could not count tokens with tiktoken (encoding: {encoding_name}): {e}")
        print("Please ensure tiktoken is installed ('pip install tiktoken') and the encoding is correct.")
        return -1

def consolidate_module(module_path: pathlib.Path, output_file: pathlib.Path, include_txt: bool = False, include_md: bool = False) -> None:
    """
    Consolidates all Python files in a module/directory into a single text file.
    Optionally includes .txt and .md files based on the provided toggles.

    Args:
        module_path: The path to the Python module/directory.
        output_file: The path to the output text file.
        include_txt: Boolean flag to include .txt files in the consolidation.
        include_md: Boolean flag to include .md files in the consolidation.
    """
    consolidated_content = []
    
    if not module_path.is_dir():
        print(f"Error: {module_path} is not a valid directory.")
        return

    print(f"Scanning directory: {module_path.resolve()}")

    file_patterns = ["*.py"]
    if include_txt:
        file_patterns.append("*.txt")
    if include_md:
        file_patterns.append("*.md")

    for pattern in file_patterns:
        for file in sorted(module_path.rglob(pattern)):
            relative_path = file.relative_to(module_path)
            header = f"--- File: {relative_path} ---\n"
            print(f"Processing: {file.resolve()}")
            try:
                with open(file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                consolidated_content.append(header)
                consolidated_content.append(content)
                consolidated_content.append(f"\n--- End File: {relative_path} ---\n\n")
            except Exception as e:
                print(f"Error reading file {file}: {e}")
                consolidated_content.append(header)
                consolidated_content.append(f"Error reading file: {e}\n")
                consolidated_content.append(f"\n--- End File: {relative_path} ---\n\n")

    full_text_output = "".join(consolidated_content)

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(full_text_output)
        print(f"Successfully consolidated module into: {output_file.resolve()}")
        
        token_count = count_tokens(full_text_output)
        if token_count != -1:
            print(f"Estimated token count (cl100k_base): {token_count}")

    except Exception as e:
        print(f"Error writing to output file {output_file}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Consolidate a Python module/directory into a single text file and count tokens."
    )
    parser.add_argument(
        "module_path", 
        type=str, 
        help="Path to the Python module or directory to consolidate."
    )
    parser.add_argument(
        "output_file", 
        type=str, 
        help="Path for the output consolidated text file."
    )

    args = parser.parse_args()

    module_p = pathlib.Path(args.module_path)
    output_p = pathlib.Path(args.output_file)

    consolidate_module(module_p, output_p, include_txt=False, include_md=True) 