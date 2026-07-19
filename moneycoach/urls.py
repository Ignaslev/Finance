from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from .views import landing, privacy, terms, contact
from .seo import robots_txt, sitemap_xml

urlpatterns = [
    path("", landing, {"language": "lt"}, name="landing"),
    path("en/", landing, {"language": "en"}, name="landing_en"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap_xml"),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("accounts/", include("accounts.urls")),
    path("register/", RedirectView.as_view(pattern_name="register", permanent=False)),
    path("login/", RedirectView.as_view(pattern_name="login", permanent=False)),
    path("logout/", auth_views.LogoutView.as_view()),
    path("privacy/", privacy, {"language": "lt"}, name="privacy"),
    path("en/privacy/", privacy, {"language": "en"}, name="privacy_en"),
    path("terms/", terms, {"language": "lt"}, name="terms"),
    path("en/terms/", terms, {"language": "en"}, name="terms_en"),
    path("contact/", contact, {"language": "lt"}, name="contact"),
    path("en/contact/", contact, {"language": "en"}, name="contact_en"),
    path("", include("finance.urls")),  # delegates /... to finance.urls

]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
