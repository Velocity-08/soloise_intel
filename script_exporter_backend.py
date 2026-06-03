import os
from pathlib import Path

ROOT_DIR = Path(".")
EXCLUDE_DIRS = {"env", ".git", "__pycache__", "node_modules"}

SCRIPT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".sh",
    ".bash",
    ".ps1",
    ".java",
    ".go",
    ".php",
    ".rb",
    ".cs"
}


def extract_scripts(folder_path):
    results = []

    for root, dirs, files in os.walk(folder_path):
        # skip virtualenvs, git metadata, and other large folders
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            file_path = Path(root) / file

            if file_path.suffix.lower() in SCRIPT_EXTENSIONS:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    results.append({
                        "name": file,
                        "path": str(file_path),
                        "code": content
                    })

                except Exception as e:
                    results.append({
                        "name": file,
                        "path": str(file_path),
                        "code": f"ERROR READING FILE: {e}"
                    })

    return results


def main():
    root = ROOT_DIR

    if not root.exists():
        print(f"Root folder not found: {root}")
        return

    print(f"\nScanning project root: {root.resolve()}")
    all_scripts = extract_scripts(root)

    output_file = "all_scripts_dump.txt"

    with open(output_file, "w", encoding="utf-8") as out:
        for script in all_scripts:
            out.write("=" * 100 + "\n")
            out.write(f"FILE NAME: {script['name']}\n")
            out.write(f"PATH: {script['path']}\n")
            out.write("=" * 100 + "\n\n")
            out.write(script["code"])
            out.write("\n\n\n")

    print(f"\nDone. Extracted {len(all_scripts)} scripts.")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()