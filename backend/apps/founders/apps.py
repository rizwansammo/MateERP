from django.apps import AppConfig


class FoundersConfig(AppConfig):
    name = "apps.founders"

    def ready(self):
        from apps.accounting.services.adapters import register_source
        from apps.approvals.services import register_executor
        from apps.files.access import register_purpose_policy

        from .services import corporate, sharing
        from .services.evidence import can_read

        register_source(
            "founder_transaction",
            {
                "post": ("founder.verify",),
                "reverse": ("founder.verify", "founder.liabilities.manage"),
            },
        )
        register_executor(
            "founder.post",
            corporate.execute_post,
            decider_permissions=("founder.verify",),
            financial=True,
            on_declined=corporate.declined,
        )
        register_executor(
            "founder.policy",
            sharing.execute_policy,
            decider_permissions=("founder.planning.manage",),
            financial=True,
            on_declined=sharing.declined_policy,
        )
        register_purpose_policy("founder_evidence", can_read)
        register_purpose_policy("personal_evidence", can_read)
