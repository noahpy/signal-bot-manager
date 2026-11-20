from django.conf import settings


def dashboard(request):
    return {"messages_page": settings.MESSAGES_PAGE}
