"""OpenAPI description of the session + CSRF authentication."""

from drf_spectacular.authentication import SessionScheme


class MateErpSessionScheme(SessionScheme):
    target_class = "apps.accounts.authentication.SessionAuthentication"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "mateerp_session"}
