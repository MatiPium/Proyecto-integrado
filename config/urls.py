"""Rutas del proyecto SGR."""

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from core import complementarios

urlpatterns = [
    path("admin/", admin.site.urls),
    path("acceso/", complementarios.SGRLoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += [path('media/<path:path>', complementarios.secure_media, name='secure_media')]
