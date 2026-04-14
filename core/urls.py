"""
URL configuration for core project.
"""

from django.contrib import admin
from django.urls import path

from dashboard.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
