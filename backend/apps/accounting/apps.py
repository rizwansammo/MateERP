from django.apps import AppConfig


class AccountingConfig(AppConfig):
    name = "apps.accounting"

    def ready(self):
        from apps.accounting.services.adapters import register_source
        from apps.approvals.services import register_executor

        from .services.posting import execute_approved

        register_executor("accounting.post", execute_approved)
        register_source(
            "cutover", {"post": ("onboarding.manage", "accounting.manage", "finance.view")}
        )
        from .services import onboarding

        register_executor(
            "historical.review",
            onboarding.execute_review,
            decider_permissions=("onboarding.manage", "accounting.manage", "finance.view"),
            financial=True,
            on_declined=onboarding.declined,
        )
        from apps.files.access import register_purpose_policy

        register_purpose_policy("historical_evidence", onboarding.can_read_evidence)
