import sys
import json 
import glob
from collections import OrderedDict, defaultdict
import re
from pathlib import Path

def extract_module_names(file_path):
    """Extract module names from a Verilog file, preserving order."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    module_pattern = r'module\s+([A-Za-z0-9_]+)\s*[\(;]'
    modules = []
    for match in re.finditer(module_pattern, content):
        module_name = match.group(1)
        if module_name not in modules:
            modules.append(module_name)
    
    return modules

def analyze_used_primitives(json_pattern):
    """Extract primitives used in example designs."""
    primitive_counts = defaultdict(int)
    
    for filename in glob.glob(json_pattern):
        with open(filename) as f:
            design = json.load(f)
            
        for module in design['modules'].values():
            for cell in module.get('cells', {}).values():
                primitive_counts[cell['type']] += 1
    
    return set(primitive_counts.keys())

def escape_markdown(text):
    """Escape underscores for markdown."""
    return text.replace('_', '\\_')

def generate_markdown_table(files_modules, column_names, apicula_primitives):
    """Generate a markdown table including Apicula usage data."""
    all_modules = []
    for modules in files_modules.values():
        for module in modules:
            if module not in all_modules:
                all_modules.append(module)
    
    headers = ['Primitive'] + list(column_names.values()) + ['Apicula']
    header_row = '| ' + ' | '.join(headers) + ' |'
    separator_row = '| ' + ' | '.join(['---' for _ in headers]) + ' |'
    
    rows = []
    for module in all_modules:
        row = [f'[[{escape_markdown(module)}]]']
        for file in files_modules.keys():
            row.append('✓' if module in files_modules[file] else '')
        row.append('✓' if module in apicula_primitives else '')
        rows.append('| ' + ' | '.join(row) + ' |')
    
    return '\n'.join([header_row, separator_row] + rows)

def main():
    if len(sys.argv) < 3 or len(sys.argv) % 2 != 1:
        print("Usage: script.py <name1> <file1> <name2> <file2> ...")
        sys.exit(1)
    
    files_modules = OrderedDict()
    column_names = {}
    
    for i in range(1, len(sys.argv), 2):
        column_name = sys.argv[i]
        file_path = sys.argv[i + 1]
        files_modules[file_path] = extract_module_names(file_path)
        column_names[file_path] = column_name
    
    # Get primitives used in examples
    apicula_primitives = analyze_used_primitives('examples/himbaechel/*-synth.json')
    
    table = generate_markdown_table(files_modules, column_names, apicula_primitives)
    print(table)

if __name__ == "__main__":
    main()
