import sys
from collections import OrderedDict
import re
from pathlib import Path

def escape_markdown(text):
    """Escape underscores for markdown."""
    return text.replace('_', '\\_')

def extract_module_names(file_path):
    """Extract module names from a Verilog file, preserving order."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all module declarations, preserving order
    module_pattern = r'module\s+([A-Za-z0-9_]+)\s*[\(;]'
    modules = []
    for match in re.finditer(module_pattern, content):
        module_name = match.group(1)
        if module_name not in modules:  # Only add if not already seen
            modules.append(module_name)
    
    return modules

def generate_markdown_table(files_modules, column_names):
    """Generate a markdown table from the collected module information."""
    # Get all modules while preserving order
    all_modules = []
    for modules in files_modules.values():
        for module in modules:
            if module not in all_modules:
                all_modules.append(module)
    
    # Create the header
    headers = ['Primitive'] + list(column_names.values())
    header_row = '| ' + ' | '.join(headers) + ' |'
    separator_row = '| ' + ' | '.join(['---' for _ in headers]) + ' |'
    
    # Create the rows
    rows = []
    for module in all_modules:
        row = [f'[[{escape_markdown(module)}]]']
        for file in files_modules.keys():
            row.append('✓' if module in files_modules[file] else '')
        rows.append('| ' + ' | '.join(row) + ' |')
    
    # Combine all parts
    table = '\n'.join([header_row, separator_row] + rows)
    return table

def main():
    if len(sys.argv) < 3 or len(sys.argv) % 2 != 1:
        print("Usage: script.py <name1> <file1> <name2> <file2> ...")
        sys.exit(1)
    
    # Process name-file pairs
    files_modules = OrderedDict()
    column_names = {}
    
    # Process pairs of arguments (name and file)
    for i in range(1, len(sys.argv), 2):
        column_name = sys.argv[i]
        file_path = sys.argv[i + 1]
        files_modules[file_path] = extract_module_names(file_path)
        column_names[file_path] = column_name
    
    # Generate and print the markdown table
    table = generate_markdown_table(files_modules, column_names)
    print(table)

if __name__ == "__main__":
    main()
