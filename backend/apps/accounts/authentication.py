from rest_framework import authentication, exceptions
from rest_framework.permissions import SAFE_METHODS


class CsrfFailed(exceptions.PermissionDenied):
    default_detail = "Security check failed. Refresh the page and try again."
    default_code = "csrf_failed"


class SessionAuthentication(authentication.SessionAuthentication):
    """Django session authentication for the API.

    Differences from DRF's class:

    * CSRF is enforced on every unsafe request, including anonymous ones
      such as sign-in (DRF only checks authenticated requests, which would
      leave login CSRF open).
    * Unauthenticated requests get 401 (with a ``WWW-Authenticate`` header)
      instead of 403, so clients can tell "sign in" from "not allowed".
    """

    def authenticate(self, request):
        if request.method not in SAFE_METHODS:
            self.enforce_csrf(request)
        user = getattr(request._request, "user", None)
        if not user or not user.is_active:
            return None
        return (user, None)

    def enforce_csrf(self, request):
        try:
            super().enforce_csrf(request)
        except exceptions.PermissionDenied as exc:
            raise CsrfFailed() from exc

    def authenticate_header(self, request) -> str:
        return 'Session realm="mateerp"'


class IntegrationAuthentication(authentication.BaseAuthentication):
    """Bearer AIA token, never a session cookie and never a login credential."""

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header:
            return None
        if not header.startswith("Bearer "):
            return None
        if header.count(" ") != 1 or len(header) > 160:
            raise exceptions.AuthenticationFailed("Invalid integration credential.")
        # Never accept bearer secrets over plain HTTP in production.
        from django.conf import settings

        if getattr(settings, "MATEERP_ENVIRONMENT", "") == "production" and not request.is_secure():
            raise exceptions.AuthenticationFailed("Integration requests require HTTPS.")
        from .integration import authenticate_token

        return authenticate_token(header[7:], request.method, request.path_info)

    def authenticate_header(self, request):
        return 'Bearer realm="mateerp-aia"'
