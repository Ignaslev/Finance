from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from .views import landing, privacy, terms, contact

urlpatterns = [
    path("", landing, name="landing"),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("accounts/", include("accounts.urls")),
    path("register/", RedirectView.as_view(pattern_name="register", permanent=False)),
    path("login/", RedirectView.as_view(pattern_name="login", permanent=False)),
    path("logout/", auth_views.LogoutView.as_view()),
    path("", include("finance.urls")),  # delegates /... to finance.urls
    path("privacy/", privacy, name="privacy"),
    path("terms/", terms, name="terms"),
    path("contact/", contact, name="contact"),

]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
