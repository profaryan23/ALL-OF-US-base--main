#!/usr/bin/env python
"""
Command-line management runner for All of Us platform.
Supports custom management commands such as `import_legacy_customers`.
"""
import sys
import os

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "import_legacy_customers":
        from management.commands.import_legacy_customers import Command
        cmd = Command()
        args = sys.argv[2:]
        if not args:
            print("Error: Missing CSV file path.\nUsage: python manage.py import_legacy_customers <path_to_csv>")
            sys.exit(1)
        cmd.handle(*args)
        return

    # If Django is installed and configured, fall back to Django's execute_from_command_line
    try:
        from django.core.management import execute_from_command_line
        execute_from_command_line(sys.argv)
    except Exception:
        print(f"All of Us Platform CLI: Command '{sys.argv[1] if len(sys.argv) > 1 else ''}'")
        print("Available commands:")
        print("  - import_legacy_customers <csv_file>")

if __name__ == "__main__":
    main()

