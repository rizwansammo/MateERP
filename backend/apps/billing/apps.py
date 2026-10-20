from django.apps import AppConfig


class BillingConfig(AppConfig):
    """Receivables: invoices, payments, receipts, credits, refunds and recurring billing."""

    name = "apps.billing"
    label = "billing"

    def ready(self) -> None:
        from apps.accounting.services.adapters import register_source
        from apps.approvals.services import register_executor

        from .services import credits, invoices, payments

        # Domain posting sources and the permission each action requires.
        register_source("invoice", {"issue": ("invoices.issue",), "void": ("invoices.issue",)})
        register_source(
            "customer_payment", {"verify": ("payments.approve",), "reverse": ("payments.approve",)}
        )
        register_source("credit_note", {"issue": ("credit_notes.manage",)})
        register_source("credit_application", {"apply": ("payments.record",)})
        register_source("customer_refund", {"pay": ("credit_notes.manage",)})

        register_executor(
            "invoice.approve", invoices.execute_approval, decider_permissions=("invoices.issue",)
        )
        register_executor(
            "payment.verify",
            payments.execute_approval,
            decider_permissions=("payments.approve",),
            financial=True,
        )
        register_executor(
            "credit_note.issue",
            credits.execute_credit_note,
            decider_permissions=("credit_notes.manage",),
            financial=True,
        )
        register_executor(
            "refund.pay",
            credits.execute_refund,
            decider_permissions=("credit_notes.manage",),
            financial=True,
        )
