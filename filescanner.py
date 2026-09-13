import os

# Files and folders to completely ignore
IGNORE_DIRS = {'.venv', '__pycache__', '.git', '.idea', '.vscode'}
ALLOWED_EXTENSIONS = {'.py'}

output_file = "project_summary.txt"

with open(output_file, "w", encoding="utf-8") as outfile:
    for root, dirs, files in os.walk("."):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            ext = os.path.splitext(file)[1]
            if ext in ALLOWED_EXTENSIONS:
                filepath = os.path.join(root, file)
                
                # We don't want to scan our own scanner!
                if file == "filescanner.py":
                    continue
                    
                outfile.write(f"\n{'='*60}\n")
                outfile.write(f"FILE: {filepath}\n")
                outfile.write(f"{'='*60}\n")
                
                try:
                    with open(filepath, "r", encoding="utf-8") as infile:
                        outfile.write(infile.read() + "\n")
                except Exception as e:
                    outfile.write(f"[Error reading file: {e}]\n")

print(f"Done! Open {output_file}, copy the contents, and paste them to your AI assistant.")
