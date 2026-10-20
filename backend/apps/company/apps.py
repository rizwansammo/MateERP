from django.apps import AppConfig
from django.db.models.signals import post_migrate


def ensure_company_defaults(**kwargs) -> None:
    from .models import ModuleSetting
    from .reference import OPTIONAL_MODULES
    from .services import get_business_settings

    for module in OPTIONAL_MODULES:
        ModuleSetting.objects.get_or_create(key=module.key)
    get_business_settings()


class CompanyConfig(AppConfig):
    """The single company profile, business settings and optional modules."""

    name = "apps.company"
    label = "company"

    def ready(self) -> None:
        from apps.files.access import register_reference_resolver

        from .services import company_file_references

        register_reference_resolver(company_file_references)
        post_migrate.connect(ensure_company_defaults, sender=self)
