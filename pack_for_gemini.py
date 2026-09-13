import os
from pathlib import Path

# --- CONFIGURATION ---
BASE_FILENAME = "codebase_part"
MAX_SIZE_MB = 50 

# FIXED: Added '.venv' to this list so it actually ignores your library files
IGNORE_DIRS = {
    '.git', '__pycache__', 'uploads', 'data', 'assets', 'env', 'venv', '.venv',
    'chroma_db', '.idea', '.vscode', 'node_modules', 'dist', 'build',
    'coverage', 'tmp', 'temp', 'logs'
}

# Changed to only include Python files
INCLUDE_EXTS = {'.py'}

def get_file_size_mb(file_path):
    return os.path.getsize(file_path) / (1024 * 1024)

def pack_project():
    project_root = Path(__file__).parent
    part_num = 1
    current_size = 0
    total_files = 0
    
    # 1. COLLECT ALL FILES FIRST
    all_files = []
    print("Scanning files...")
    
    for root, dirs, files in os.walk(project_root):
        # Filter dirs in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            file_path = Path(root) / file
            
            # Skip the packer script and output files
            if file == "pack_for_gemini.py" or file.startswith(BASE_FILENAME):
                continue
            
            if file_path.suffix in INCLUDE_EXTS:
                all_files.append(file_path)

    # 2. SORT FILES (Alphabetical sorting is sufficient now)
    all_files.sort()

    # 3. WRITE FILES
    out_f = open(f"{BASE_FILENAME}_{part_num}.txt", 'w', encoding='utf-8')
    out_f.write(f"PROJECT CONTEXT - PART {part_num}\n")
    out_f.write(f"================================\n\n")

    print(f"Starting Part {part_num}...")

    for file_path in all_files:
        try:
            rel_path = file_path.relative_to(project_root)
            
            # Prepare the content block
            header = f"\n{'='*60}\nFILE: {rel_path}\n{'='*60}\n"
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as in_f:
                content = in_f.read()
                
            full_block = header + content + "\n"
            block_size_mb = len(full_block.encode('utf-8')) / (1024 * 1024)

            # Check if adding this file exceeds the limit
            if current_size + block_size_mb > MAX_SIZE_MB:
                out_f.close()
                print(f"Finished Part {part_num} ({current_size:.2f} MB)")
                
                part_num += 1
                current_size = 0
                out_f = open(f"{BASE_FILENAME}_{part_num}.txt", 'w', encoding='utf-8')
                out_f.write(f"PROJECT CONTEXT - PART {part_num}\n")
                out_f.write(f"================================\n\n")
                print(f"Starting Part {part_num}...")
            
            # Write content
            out_f.write(full_block)
            current_size += block_size_mb
            total_files += 1
            print(f"Packed: {rel_path}")
            
        except Exception as e:
            print(f"Error reading {file_path.name}: {e}")

    out_f.close()
    print(f"\nDone! Packed {total_files} files into {part_num} parts.")

if __name__ == "__main__":
    pack_project()