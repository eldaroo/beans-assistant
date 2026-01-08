"""Fix indentation issues caused by removing try: blocks."""
import re
from pathlib import Path

def fix_indentation(filepath: Path):
    """Fix over-indented code after try: removal."""
    print(f"Fixing indentation in {filepath.name}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fixed_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this line is a docstring end followed by over-indented code
        if line.strip() == '"""' and i + 1 < len(lines):
            # Add the docstring line
            fixed_lines.append(line)
            i += 1

            # Check if next line is over-indented (8+ spaces)
            if i < len(lines):
                next_line = lines[i]
                if next_line.startswith('        ') and not next_line.strip().startswith(('"""', "'''")):
                    # Over-indented! Dedent until we hit a line with 4 or fewer spaces
                    print(f"  Dedenting from line {i + 1}")
                    while i < len(lines):
                        line = lines[i]
                        if line.strip() and line.startswith('        '):
                            # Dedent by 4 spaces
                            fixed_lines.append(line[4:])
                        elif line.strip() and not line.startswith('    '):
                            # Back to normal indentation
                            fixed_lines.append(line)
                            i += 1
                            break
                        else:
                            # Empty line or properly indented
                            fixed_lines.append(line)

                        i += 1
                    continue

        fixed_lines.append(line)
        i += 1

    # Write fixed content
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)

    print(f"[OK] Fixed {filepath.name}")

if __name__ == '__main__':
    backend_dir = Path(__file__).parent / 'backend' / 'api'

    files_to_fix = [
        'expenses.py',
        'analytics.py'
    ]

    for filename in files_to_fix:
        filepath = backend_dir / filename
        if filepath.exists():
            fix_indentation(filepath)
        else:
            print(f"[WARN] File not found: {filename}")

    print("\nDone! Files fixed.")
