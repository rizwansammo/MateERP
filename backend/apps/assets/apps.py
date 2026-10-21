from django.apps import AppConfig


class AssetsConfig(AppConfig):
    name = "apps.assets"
    label = "assets"

    def ready(self):
        from apps.accounting.services.adapters import register_source
        from apps.approvals.services import register_executor
        from apps.files.access import register_purpose_policy

        from . import services

        register_source(
            "asset_event",
            {
                "post": ("assets.manage", "assets.post", "finance.view"),
                "reverse": ("assets.manage", "assets.post", "finance.view", "accounting.manage"),
            },
        )
        register_executor(
            "asset.post",
            services.execute_approval,
            decider_permissions=("assets.manage", "assets.post", "finance.view"),
            financial=True,
            on_declined=services.declined,
        )
        register_purpose_policy("asset_evidence", services.can_read_evidence)
