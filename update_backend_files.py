"""
Quick script to update remaining backend API files to remove TenantManager dependency.
"""
import re
from pathlib import Path

def update_file(filepath: Path):
    """Update a backend API file to remove TenantManager."""
    print(f"Updating {filepath.name}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove sqlite3 import
    content = re.sub(r'import sqlite3\n', '', content)

    # Remove TenantManager import
    content = re.sub(r'from tenant_manager import TenantManager\n', '', content)

    # Add datetime import if not present
    if 'from datetime import datetime' not in content:
        content = content.replace(
            'from pathlib import Path',
            'from pathlib import Path\nfrom datetime import datetime'
        )

    # Remove _get_tenant_db_uri function
    content = re.sub(
        r'\n\ndef _get_tenant_db_uri\(phone: str\) -> str:.*?return tenant_manager\.get_tenant_db_path\(phone\)\n',
        '\n',
        content,
        flags=re.DOTALL
    )

    # Replace sqlite3.Row with dict in type hints
    content = content.replace('row: sqlite3.Row', 'row: dict')

    # Remove database.DB_PATH manipulation patterns
    # Pattern 1: assignment and restoration
    content = re.sub(
        r'\s+db_uri = _get_tenant_db_uri\(phone\)\n\s+original_db = database\.DB_PATH\n\s+database\.DB_PATH = db_uri\n\s+try:',
        '\n    try:',
        content
    )

    # Pattern 2: finally blocks that restore DB_PATH
    content = re.sub(
        r'\s+finally:\n\s+database\.DB_PATH = original_db\n',
        '\n',
        content
    )

    # Replace SQL placeholders ? with %s for PostgreSQL
    content = re.sub(
        r'LIMIT \? OFFSET \?',
        'LIMIT %s OFFSET %s',
        content
    )

    content = re.sub(
        r'WHERE id = \?',
        'WHERE id = %s',
        content
    )

    content = re.sub(
        r'WHERE sale_id = \?',
        'WHERE sale_id = %s',
        content
    )

    # Write updated content
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[OK] Updated {filepath.name}")

if __name__ == '__main__':
    backend_dir = Path(__file__).parent / 'backend' / 'api'

    files_to_update = [
        'expenses.py',
        'sales.py',
        'analytics.py'
    ]

    for filename in files_to_update:
        filepath = backend_dir / filename
        if filepath.exists():
            update_file(filepath)
        else:
            print(f"[WARN] File not found: {filename}")

    print("\nDone! Files updated successfully.")
