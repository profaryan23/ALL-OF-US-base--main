"""
CRM URL Configuration for All of Us platform.
Defines URL patterns for customer management and CRM actions.
Compatible with standard Django urlpatterns format.
"""
from typing import Callable, Any, List

try:
    from django.urls import path
except ImportError:
    class PathRule:
        def __init__(self, route: str, view: Callable, name: str = ""):
            self.route = route
            self.view = view
            self.name = name

        def __repr__(self):
            return f"path({self.route!r}, {self.view.__name__}, name={self.name!r})"

    def path(route: str, view: Callable, name: str = "") -> PathRule:
        return PathRule(route, view, name=name)

from views import add_customer_view

app_name = "crm"

urlpatterns = [
    path("admin/crm/customers/add", add_customer_view, name="add_customer_view"),
    path("admin/crm/add-customer", add_customer_view, name="add_customer"),
]

