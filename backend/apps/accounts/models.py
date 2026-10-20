from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Project user model.

    Defined before the first migration so that Phase 2 can extend it without
    the costly migration that swapping ``AUTH_USER_MODEL`` later would need.
    """

    class Meta:
        db_table = "accounts_user"
        verbose_name = "user"
        verbose_name_plural = "users"
