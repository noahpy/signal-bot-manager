from django.conf import settings
from django.contrib.auth.views import redirect_to_login

# Paths that never require a dashboard login: machine endpoints authenticate
# themselves (webhook token, API bearer token), the rest is the login flow.
EXEMPT_PREFIXES = ("/accounts/", "/webhook/", "/api/", "/static/", "/admin/")


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            settings.DASHBOARD_REQUIRE_LOGIN
            and not request.user.is_authenticated
            and not request.path.startswith(EXEMPT_PREFIXES)
        ):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)
