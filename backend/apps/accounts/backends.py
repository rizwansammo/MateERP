from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsernameOrEmailBackend(ModelBackend):
    """Sign in with a username or an email address (case-insensitive).

    Inactive users never authenticate. When no single account matches, the
    password hasher still runs so response timing does not reveal whether
    an account exists.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or password is None:
            return None
        identifier = username.strip()
        query = Q(username__iexact=identifier)
        if "@" in identifier:
            query |= Q(email__iexact=identifier)

        user_model = get_user_model()
        matches = list(user_model._default_manager.filter(query)[:2])
        if len(matches) != 1:
            user_model().set_password(password)
            return None
        user = matches[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
