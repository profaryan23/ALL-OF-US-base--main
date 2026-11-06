"""
Django management command wrapper for importing legacy customer records.
Usage:
    python manage.py import_legacy_customers <path_to_csv>
"""
import sys
import os

# Add root directory to python path if not present
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from import_legacy_customers import Command, import_legacy_customers, get_or_create

__all__ = ["Command", "import_legacy_customers", "get_or_create"]

