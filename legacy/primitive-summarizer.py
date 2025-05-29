import pypdf
import re
from pathlib import Path
from typing import List, Dict
import ollama
import os
import json
import glob
from collections import defaultdict
from pypdf import PdfReader

def get_outline_tree(reader: PdfReader) -> List[Dict]:
    """
    Extract the complete outline/bookmark structure from a PDF.
    
    Args:
        reader (PdfReader): PyPDF Reader object
        
    Returns:
        list: List of dictionaries containing outline information
    """
    outlines = reader.outline
    
    if not outlines:
        return []

    def extract_destinations(outline_item):
        """Recursively extract all destinations from an outline item"""
        if isinstance(outline_item, list):
            return [item for i in outline_item for item in extract_destinations(i)]
            
        if not hasattr(outline_item, '__getitem__'):
            return []
            
        try:
            title = outline_item.get('/Title', 'Untitled')
            page_num = reader.get_destination_page_number(outline_item)
            
            result = [{
                'title': title,
                'page': page_num
            }]
            
            # Check for children (/First and /Next form a linked list of children)
            if '/First' in outline_item:
                result.extend(extract_destinations(outline_item['/First']))
            
            # Check for siblings
            if '/Next' in outline_item:
                result.extend(extract_destinations(outline_item['/Next']))
                
            return result
            
        except Exception as e:
            print(f"Error processing outline item: {e}")
            return []

    return extract_destinations(outlines)

def find_sections_in_outline(outline: List[Dict], pattern: str, flags: int = re.IGNORECASE) -> List[Dict]:
    """
    Search for sections in the outline that match the regex pattern.
    
    Args:
        outline (list): Outline structure from get_outline_tree
        pattern (str): Regular expression pattern to search for
        flags (int): Regular expression flags (default: case insensitive)
        
    Returns:
        list: Matching sections with their details
    """
    matches = []
    
    try:
        regex = re.compile(pattern, flags)
        
        for item in outline:
            title = item.get('title', '')
            if regex.search(title):
                matches.append(item)
    
    except re.error as e:
        print(f"Invalid regular expression: {e}")
        return []
        
    return matches

def print_outline(outline: List[Dict]) -> None:
    """
    Print the outline structure.
    
    Args:
        outline (list): Outline structure from get_outline_tree
    """
    if not outline:
        return
        
    for item in outline:
        title = item.get('title', 'Untitled')
        page = item.get('page', 0)
        print(f"- {title} (Page {page + 1})")


def analyze_primitives(json_pattern):
    primitive_counts = defaultdict(int)
    
    for filename in glob.glob(json_pattern):
        with open(filename) as f:
            design = json.load(f)
            
        for module in design['modules'].values():
            for cell in module.get('cells', {}).values():
                primitive_counts[cell['type']] += 1
    
    # Sort by count descending
    return dict(sorted(primitive_counts.items(), key=lambda x: x[1], reverse=True))


def generate_summary(pdfs, primitive_name: str) -> str:
    """Generate markdown summary using Ollama."""

    doc_sections = []
    for reader in pdfs:
        outline = get_outline_tree(reader)
        matches = find_sections_in_outline(outline, rf"^[0-9\.]+ +{primitive_name}$")
        if matches:
            pages = [reader.pages[match['page']].extract_text() for match in matches]
            doc_sections.append(pages)

    doc_context = "\n\n".join(
        "\n".join(pages)
        for pages in doc_sections
    )
    
    description = ""
    if doc_context:
        prompt = f"""
{doc_context}

Summarizing the functionality of the Gowin {primitive_name} primitive.
Stick to the provided facts and do not make assumptions.
Write only the requested paragraph and nothing else.
"""
        print(prompt)
        response = ollama.generate(
            model='llama3.1:8b',
            prompt=prompt,
        )
        description = escape_markdown(response["response"])
        print(description)
    return description


def escape_markdown(text):
    return text.replace('_', '\\_')

def format_bits(bits):
    if isinstance(bits, list):
        if len(bits) == 1:
            return "1"
        else:
            return str(len(bits))
    return "1"

def get_default_param_value(value):
    if isinstance(value, str) and all(c in '01' for c in value):
        decimal_value = int(value, 2)
        return f"{decimal_value} (0b{value})"
    return value

def generate_module_doc(module_name, module_data, supported, pdfs):
    module_doc = []
    
    module_doc.append(generate_summary(pdfs, module_name))
    
    module_doc.append("\n")
    if supported:
        module_doc.append("This device is supported in Apicula.")
    else:
        module_doc.append("This device is not yet supported in Apicula")

    # Ports table
    if module_data.get('ports'):
        module_doc.append("## Ports\n")
        module_doc.append("| Port | Size | Direction |")
        module_doc.append("|------|------|-----------|")
        
        for port_name, port_data in sorted(module_data['ports'].items()):
            size = format_bits(port_data['bits'])
            direction = port_data['direction']
            module_doc.append(f"| {escape_markdown(port_name)} | {size} | {direction} |")
        module_doc.append("\n")
    
    # Parameters table
    if module_data.get('parameter_default_values'):
        module_doc.append("## Parameters\n")
        module_doc.append("| Parameter | Default Value |")
        module_doc.append("|-----------|---------------|")
        
        for param_name, param_value in sorted(module_data['parameter_default_values'].items()):
            default_value = get_default_param_value(param_value)
            module_doc.append(f"| {escape_markdown(param_name)} | {default_value} |")
        module_doc.append("\n")
    
    # Verilog instantiation template
    module_doc.append("## Verilog Instantiation")
    module_doc.append("```verilog")
    
    # Generate instantiation
    instance = []
    
    # Add parameters if they exist
    if module_data.get('parameter_default_values'):
        instance.append(f"{module_name} #(")
        param_list = []
        for param_name in sorted(module_data['parameter_default_values'].keys()):
            param_list.append(f"    .{param_name}({param_name})")
        instance.append(",\n".join(param_list))
        instance.append(f") {module_name.lower()}_inst (")
    else:
        instance.append(f"{module_name} {module_name.lower()}_inst (")
    
    # Add ports
    if module_data.get('ports'):
        port_list = []
        for port_name in sorted(module_data['ports'].keys()):
            port_list.append(f"    .{port_name}({port_name})")
        instance.append(",\n".join(port_list))
    
    instance.append(");")
    module_doc.append("\n".join(instance))
    module_doc.append("```\n")
    
    return "\n".join(module_doc)

def process_json_file(json_data, stats, pdfs, output_dir):
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each module
    for module_name, module_data in sorted(json_data['modules'].items()):
        # Generate documentation for this module
        supported = module_name in stats
        doc = generate_module_doc(module_name, module_data, supported, pdfs)
        
        # Write to file
        filename = os.path.join(output_dir, f"{module_name}.md")
        with open(filename, 'w') as f:
            f.write(doc)

def main():
    # Create docs directory
    output_dir = "../apicula.wiki"
    
    # Read and process the JSON file
    with open('prims.json', 'r') as f:
        data = json.load(f)
    
    stats = analyze_primitives('examples/himbaechel/*-synth.json')

    pdfs = []
    for pdf_path in Path("~/Documents/gowin/").expanduser().glob("*.pdf"):
        pdfs.append(pypdf.PdfReader(pdf_path))
    
    # Generate documentation
    process_json_file(data, stats, pdfs, output_dir)
    print(f"Documentation generated in {output_dir}/")

if __name__ == "__main__":
    main()