from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import landing, privacy, terms, contact
from accounts.views import register as accounts_register

urlpatterns = [
    path("", landing, name="landing"),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("register/", accounts_register, name="register"),
    path("", include("finance.urls")),  # delegates /... to finance.urls
    path("accounts/", include("accounts.urls")),
    path("privacy/", privacy, name="privacy"),
    path("terms/", terms, name="terms"),
    path("contact/", contact, name="contact"),

]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)