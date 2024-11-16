import argparse
import pypdf
import re
from pathlib import Path
from typing import List, Dict
import ollama
import os
import json
import glob
from collections import defaultdict

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

class CodeScanner:
    def __init__(self, primitive_name: str):
        self.primitive_name = primitive_name
        self.module_pattern = rf"module\s+{primitive_name}\s*\([^;]*;\s*(.*?)\s*endmodule"
        self.usage_pattern = rf"\b{primitive_name}\s+[a-zA-Z0-9_]+\s*\("
    
    def scan_file(self, file_path: Path, scan_for_usage: bool = False) -> str:
        if not file_path.exists():
            return ""
        
        with open(file_path) as f:
            content = f.read()
        
        if scan_for_usage:
            return content if re.search(self.usage_pattern, content) else ""
        else:
            match = re.search(self.module_pattern, content, re.DOTALL)
            return match.group(0) if match else ""
    
    def scan_directory(self, directory: Path, scan_for_usage: bool = False) -> Dict[Path, str]:
        results = {}
        for file_path in directory.rglob("*.v"):
            if content := self.scan_file(file_path, scan_for_usage):
                results[os.path.basename(file_path)] = content
        return results

class DocScanner:
    def __init__(self, primitive_name: str, min_matches: int = 3):
        self.primitive_name = primitive_name.lower()
        self.min_matches = min_matches
    
    def _count_whole_word_matches(self, text: str) -> int:
        pattern = rf'\b{self.primitive_name}\b'
        return len(re.findall(pattern, text.lower()))
    
    def scan_pdf(self, pdf_path: Path) -> List[str]:
        if not pdf_path.exists():
            return []
        
        reader = pypdf.PdfReader(pdf_path)
        relevant_pages = []
        
        for page in reader.pages:
            text = page.extract_text()
            if self._count_whole_word_matches(text) >= self.min_matches:
                relevant_pages.append(text)
        
        return relevant_pages
    
    def scan_directory(self, directory: Path) -> Dict[Path, List[str]]:
        results = {}
        for pdf_path in directory.rglob("*.pdf"):
            if pages := self.scan_pdf(pdf_path):
                results[os.path.basename(pdf_path)] = pages
        return results

def generate_summary(code_sections: Dict[Path, str], 
                    doc_sections: Dict[Path, List[str]], 
                    example_sections: Dict[Path, str],
                    supported: bool,
                    primitive_name: str) -> str:
    """Generate markdown summary using Ollama."""
    code_context = "\n\n".join(f"From {path}:\n{code}" 
                              for path, code in code_sections.items())
    
    doc_context = "\n\n".join(
        f"From {path}:\n" + "\n".join(pages)
        for path, pages in doc_sections.items()
    )
    
    example_context = "\n\n".join(f"Example from {path}:\n{code}"
                                 for path, code in example_sections.items())

    sections = []
    if code_context:
        sections.append(("Implementation:", code_context))
    if doc_context:
        sections.append(("Documentation:", doc_context))
    if example_context:
        sections.append(("Usage Examples:", example_context))

    list_sections = []
    if doc_context:
        list_sections.append("- Brief description")
    
    if supported:
        list_sections.append("- Apicula support (this device is supported)")
    else:
        list_sections.append("- Apicula support (this device is not yet supported)")

    list_sections.extend([
        "- Port list with descriptions",
        "- Parameters",
    ])

    if example_context:
        list_sections.append("- Usage example")

    context = "\n\n".join(f"{title}\n{content}" for title, content in sections)

    
    prompt = f"""You are an expert in FPGA architecture and Verilog HDL. Generate detailed technical documentation about Gowin primitives in Apicula.

Create a markdown summary about {primitive_name} support in Apicula based on this information:

{context}

Include the following sections:
{"\n".join(list_sections)}
- Sources

Do not assume the meaning of things.
Stick to the facts.
Do not mention what information was or wasn't provided.
Do not say "provided".

Format in markdown with appropriate headers."""

    print(prompt)
    response = ollama.generate(
        model='qwen2.5-coder:14b',
        prompt=prompt,
        options={"temperature":0.1}
    )
    
    return response['response']

def parse_args():
    parser = argparse.ArgumentParser(description="Generate FPGA primitive documentation")
    parser.add_argument("primitive_name", help="Name of primitive to document")
    parser.add_argument("--code", "-c", type=Path, nargs='+', required=True,
                       help="Paths to Verilog source files or directories")
    parser.add_argument("--docs", "-d", type=Path, nargs='+', required=True,
                       help="Paths to PDF documentation files or directories")
    parser.add_argument("--examples", "-e", type=Path, nargs='+',
                       help="Paths to example Verilog files or directories")
    parser.add_argument("--output", "-o", type=Path, help="Output markdown file")
    parser.add_argument("--min-matches", type=int, default=3,
                       help="Minimum whole-word matches for PDF page inclusion")
    return parser.parse_args()

def main():
    args = parse_args()
    
    try:
        # Scan for code
        code_scanner = CodeScanner(args.primitive_name)
        code_sections = {}
        
        for path in args.code:
            if path.is_dir():
                code_sections.update(code_scanner.scan_directory(path))
            else:
                if content := code_scanner.scan_file(path):
                    code_sections[os.path.basename(path)] = content
        
        if not code_sections:
            raise ValueError(f"Primitive {args.primitive_name} not found in provided code paths")
        
        # Scan for documentation
        doc_scanner = DocScanner(args.primitive_name, args.min_matches)
        doc_sections = {}
        
        for path in args.docs:
            if path.is_dir():
                doc_sections.update(doc_scanner.scan_directory(path))
            else:
                if pages := doc_scanner.scan_pdf(path):
                    doc_sections[os.path.basename(path)] = pages
        
        if not doc_sections:
            print("Warning: No documentation found in provided PDF paths")
            
        # Scan for examples
        example_sections = {}
        if args.examples:
            for path in args.examples:
                if path.is_dir():
                    example_sections.update(code_scanner.scan_directory(path, scan_for_usage=True))
                else:
                    if content := code_scanner.scan_file(path, scan_for_usage=True):
                        example_sections[path] = content
        
        stats = analyze_primitives('examples/himbaechel/*-synth.json')
        supported = args.primitive_name in stats
        # Generate summary
        summary = generate_summary(code_sections, doc_sections, example_sections, supported, args.primitive_name)
        
        if args.output:
            args.output.write_text(summary)
            print(f"Summary written to {args.output}")
        else:
            print(summary)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
