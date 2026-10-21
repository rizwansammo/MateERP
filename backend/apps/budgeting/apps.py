from django.apps import AppConfig


class BudgetingConfig(AppConfig):
    name = "apps.budgeting"
    label = "budgeting"

    def ready(self):
        from apps.approvals.services import register_executor

        from . import services

        register_executor(
            "budget.publish",
            services.execute_approval,
            decider_permissions=("budgets.approve", "finance.view"),
            financial=True,
            on_declined=services.declined,
        )
