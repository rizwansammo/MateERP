from django.apps import AppConfig


class InventoryConfig(AppConfig):
    name = "apps.inventory"
    label = "inventory"

    def ready(self):
        from apps.accounting.services.adapters import register_source
        from apps.approvals.services import register_executor

        from . import counts

        register_source("stock_movement", {"post": ("inventory.post",)})
        register_executor(
            "stock_count.post",
            counts.execute,
            decider_permissions=("inventory.manage", "inventory.post", "finance.view"),
            financial=True,
            on_declined=counts.declined,
        )
