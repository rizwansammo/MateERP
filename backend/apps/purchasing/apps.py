from django.apps import AppConfig


class PurchasingConfig(AppConfig):
    """Payables: vendors, bills, expenses, recurring expenses and vendor payments."""

    name = "apps.purchasing"
    label = "purchasing"

    def ready(self) -> None:
        from apps.accounting.services.adapters import register_source
        from apps.approvals.services import register_executor

        from .services import payables, payments

        register_source("vendor_bill", {"post": ("bills.manage",), "void": ("bills.manage",)})
        register_source("expense", {"post": ("expenses.manage",), "void": ("expenses.manage",)})
        register_source(
            "vendor_payment",
            {"pay": ("vendor_payments.manage",), "reverse": ("vendor_payments.manage",)},
        )
        register_executor(
            "vendor_bill.post",
            payables.execute_bill,
            decider_permissions=("bills.manage",),
            financial=True,
        )
        register_executor(
            "expense.post",
            payables.execute_expense,
            decider_permissions=("expenses.manage",),
            financial=True,
        )
        register_executor(
            "vendor_payment.post",
            payments.execute_payment,
            decider_permissions=("vendor_payments.manage",),
            financial=True,
        )
