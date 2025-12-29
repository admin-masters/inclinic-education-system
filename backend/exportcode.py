import os
import sys
from pathlib import Path

# === Get Target Directory ===
if len(sys.argv) > 1:
    ROOT_DIR = Path(sys.argv[1]).resolve()
else:
    ROOT_DIR = Path.cwd()

OUTPUT_FILE = ROOT_DIR / 'all_code_export.txt'

# === Configuration ===
ALLOWED_EXTENSIONS = ['.py', '.js', '.ts', '.html', '.css', '.json', '.md']
EXCLUDED_DIRS = {'venv', '__pycache__', 'migrations', 'node_modules', 'Lib', 'site-packages', 'env', '.git', '.idea', '.vscode'}

def has_allowed_extension(filename):
    return any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS)

print(f"📁 Scanning directory: {ROOT_DIR}")
print(f"📄 Writing output to: {OUTPUT_FILE}")

with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
    for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
        # Exclude unwanted directories
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]

        for filename in filenames:
            if has_allowed_extension(filename):
                filepath = Path(dirpath) / filename
                relative_path = filepath.relative_to(ROOT_DIR)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as infile:
                        content = infile.read()
                        outfile.write(f"\n\n===== FILE: {relative_path} =====\n")
                        outfile.write(content)
                except Exception as e:
                    print(f"❌ Failed to read {relative_path}: {e}")

print(f"\n✅ All code files exported successfully to: {OUTPUT_FILE}")
