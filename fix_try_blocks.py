"""Fix orphaned try blocks in backend API files."""
import re
from pathlib import Path

def fix_orphaned_try_blocks(filepath: Path):
    """Remove try blocks that have no except/finally."""
    print(f"Fixing {filepath.name}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find and remove orphaned try: blocks that have no except or finally
    # Pattern: try: followed by code, then return/function definition (no except/finally)
    # We'll look for: "try:" followed by indented code, then a line with less indentation and no except/finally

    lines = content.split('\n')
    fixed_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this is a try: line
        if line.strip() == 'try:':
            # Get the indentation of the try line
            try_indent = len(line) - len(line.lstrip())

            # Look ahead to see if there's an except or finally
            j = i + 1
            has_except_finally = False

            while j < len(lines):
                next_line = lines[j]
                if next_line.strip():  # Non-empty line
                    next_indent = len(next_line) - len(next_line.lstrip())

                    # If we're back to the same or less indentation
                    if next_indent <= try_indent:
                        # Check if it's except or finally
                        if next_line.strip().startswith(('except', 'finally')):
                            has_except_finally = True
                        break

                j += 1

            # If no except/finally found, skip the try: line
            if not has_except_finally:
                print(f"  Removed orphaned try: at line {i + 1}")
                i += 1  # Skip this line
                continue

        fixed_lines.append(line)
        i += 1

    # Write fixed content
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(fixed_lines))

    print(f"[OK] Fixed {filepath.name}")

if __name__ == '__main__':
    backend_dir = Path(__file__).parent / 'backend' / 'api'

    files_to_fix = [
        'sales.py',
        'expenses.py',
        'analytics.py'
    ]

    for filename in files_to_fix:
        filepath = backend_dir / filename
        if filepath.exists():
            fix_orphaned_try_blocks(filepath)
        else:
            print(f"[WARN] File not found: {filename}")

    print("\nDone! Files fixed.")
