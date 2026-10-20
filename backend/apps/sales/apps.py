from django.apps import AppConfig


class SalesConfig(AppConfig):
    """Customers, contacts, projects, billing items and sales orders (no ledger effect)."""

    name = "apps.sales"
    label = "sales"
