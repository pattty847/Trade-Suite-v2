import pandas as pd
import json # For custom JSON pretty printing if needed, though to_json might suffice

def write_output(df: pd.DataFrame, output_config: dict, title: str | None = None):
    """
    Writes or prints the DataFrame according to the specified output configuration.

    Args:
        df (pd.DataFrame): The DataFrame to output.
        output_config (dict): A dictionary containing 'format' (str) and 'path' (str or None).
                              If 'path' is None, output is printed to stdout.
        title (str, optional): A title to prepend to the output, especially for stdout.
    """
    if not isinstance(df, pd.DataFrame):
        print(f"Error: Expected a Pandas DataFrame for output, but got {type(df)}.")
        return

    output_format = output_config.get('format', 'text').lower()
    output_path = output_config.get('path')

    output_content = ""
    if title:
        output_content += f"--- {title} ---\n"

    if output_format == 'csv':
        if output_path:
            try:
                df.to_csv(output_path, index=False)
                print(f"Successfully wrote CSV to {output_path}")
            except Exception as e:
                print(f"Error writing CSV to {output_path}: {e}")
        else:
            output_content += df.to_csv(index=False)
            print(output_content)
    elif output_format == 'json':
        if output_path:
            try:
                df.to_json(output_path, orient='records', indent=2)
                print(f"Successfully wrote JSON to {output_path}")
            except Exception as e:
                print(f"Error writing JSON to {output_path}: {e}")
        else:
            output_content += df.to_json(orient='records', indent=2)
            print(output_content)
    elif output_format == 'markdown':
        # For markdown, we usually want to see it in the console for redirection.
        # If a path is given, we can write it, though it's less common for direct .md generation this way.
        md_string = df.to_markdown(index=False)
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    if title: # Write title to file as well
                        f.write(f"# {title}\n\n")
                    f.write(md_string)
                print(f"Successfully wrote Markdown to {output_path}")
            except Exception as e:
                print(f"Error writing Markdown to {output_path}: {e}")
        else:
            output_content += md_string
            print(output_content)
    elif output_format == 'text': # Simple text output
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    if title:
                         f.write(f"--- {title} ---\n")
                    f.write(df.to_string(index=False))
                    f.write("\n-----------------------------------------------------------\n")
                print(f"Successfully wrote text to {output_path}")
            except Exception as e:
                print(f"Error writing text to {output_path}: {e}")
        else:
            output_content += df.to_string(index=False)
            output_content += "\n-----------------------------------------------------------\n"
            print(output_content)
    else:
        print(f"Warning: Unsupported output format '{output_format}'. Supported formats: csv, json, markdown, text.")

# Example Usage (for testing, can be removed later)
if __name__ == '__main__':
    data = {
        'col1': [1, 2, 3],
        'col2': ['A', 'B', 'C'],
        'col3': [0.1, 0.2, 0.3]
    }
    sample_df = pd.DataFrame(data)

    print("\nTesting CSV to stdout:")
    write_output(sample_df, {'format': 'csv', 'path': None}, title="Sample CSV Data")

    print("\nTesting JSON to file:")
    write_output(sample_df, {'format': 'json', 'path': 'sample_output.json'}, title="Sample JSON Data")

    print("\nTesting Markdown to stdout:")
    write_output(sample_df, {'format': 'markdown', 'path': None}, title="Sample Markdown Data")
    
    print("\nTesting Text to file:")
    write_output(sample_df, {'format': 'text', 'path': 'sample_output.txt'}, title="Sample Text Data")
    
    print("\nTesting unsupported format:")
    write_output(sample_df, {'format': 'xml', 'path': None}, title="Sample XML Data")

    print("\nTesting CSV to file:")
    write_output(sample_df, {'format': 'csv', 'path': 'sample_output.csv'}, title="Sample CSV Data File")
    
    print("\nTesting Markdown to file:")
    write_output(sample_df, {'format': 'markdown', 'path': 'sample_output.md'}, title="Sample MD Data File")

    # Test with None df
    # write_output(None, {'format': 'text', 'path': None}, title="Test None DF")

    print("\nEnsure files were created: sample_output.json, sample_output.txt, sample_output.csv, sample_output.md") 