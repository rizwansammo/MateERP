from django.apps import AppConfig


class PurchasingConfig(AppConfig):
    """Payables: vendors, bills, expenses, recurring expenses and vendor payments."""

    name = "apps.purchasing"
    label = "purchasing"

    def ready(self) -> None:
        from apps.accounting.services.adapters import register_source
        from apps.approvals.services import register_executor
        from apps.files.access import register_purpose_policy

        from .services import costing, payables, payments, procurement, returns

        register_purpose_policy("procurement_evidence", procurement.can_read_evidence)

        register_source("vendor_bill", {"post": ("bills.manage",), "void": ("bills.manage",)})
        register_source("expense", {"post": ("expenses.manage",), "void": ("expenses.manage",)})
        register_source("goods_receipt", {"receive": ("procurement.manage", "inventory.post")})
        register_source("supplier_return", {"post": ("procurement.manage", "inventory.post")})
        register_executor(
            "supplier_return.post",
            returns.execute,
            decider_permissions=(
                "procurement.manage",
                "procurement.approve",
                "inventory.post",
                "finance.view",
            ),
            financial=True,
        )
        register_source(
            "receipt_cost",
            {"post": ("procurement.manage", "procurement.approve", "inventory.post")},
        )
        register_executor(
            "receipt_cost.post",
            costing.execute,
            decider_permissions=(
                "procurement.manage",
                "procurement.approve",
                "inventory.post",
                "finance.view",
            ),
            financial=True,
        )
        register_executor(
            "purchase_order.approve",
            procurement.execute_approval,
            decider_permissions=("procurement.approve", "finance.view"),
            financial=True,
            on_declined=procurement.declined,
        )
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
