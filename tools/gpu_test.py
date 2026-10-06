import os
import glob
import sys

# Find where llama-cpp-python is installed
site_packages = next(p for p in sys.path if 'site-packages' in p)
base_path = os.path.join(site_packages, "llama_cpp")

print(f"🔎 Inspecting Folder: {base_path}\n")

# Find ALL dll files
dll_files = glob.glob(os.path.join(base_path, "lib", "*.dll"))

if not dll_files:
    print("❌ No DLL found!")
else:
    print(f"{'FILENAME':<25} {'SIZE (MB)':<10} {'TYPE'}")
    print("-" * 45)
    
    for file_path in dll_files:
        file_name = os.path.basename(file_path)
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        # DNA Check per file
        with open(file_path, "rb") as f:
            content = f.read()
            if b"CUDA" in content or b"nvcuda" in content:
                file_type = "🟢 GPU ENGINE"
            else:
                file_type = "⚪ Helper/CPU"
        
        print(f"{file_name:<25} {size_mb:<10.2f} {file_type}")

print("\n---------------------------------------------")
print("✅ CONCLUSION: If you see a 'GPU ENGINE' file above")
print("               that is over 100MB, you are set!")