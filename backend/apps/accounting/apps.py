from django.apps import AppConfig


class AccountingConfig(AppConfig):
    name = "apps.accounting"

    def ready(self):
        from apps.approvals.services import register_executor

        from .services.posting import execute_approved

        register_executor("accounting.post", execute_approved)
