from django.apps import AppConfig


class OwnershipConfig(AppConfig):
    name = "apps.ownership"

    def ready(self):
        from apps.approvals.services import register_executor
        from apps.files.access import register_purpose_policy
        from apps.founders.services.evidence import can_read

        from .services.register import declined, execute_review

        register_executor(
            "ownership.review",
            execute_review,
            decider_permissions=("ownership.approve",),
            financial=True,
            on_declined=declined,
        )
        register_purpose_policy("ownership_evidence", can_read)
