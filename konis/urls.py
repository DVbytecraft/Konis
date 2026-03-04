"""
URL configuration for konis project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from ventes.views import facture_pdf, facture_print, ticket_print

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("ventes/ticket/<int:ticket_id>/print/", ticket_print, name="ticket-print"),
    path("ventes/facture/<int:facture_id>/print/", facture_print, name="facture-print"),
    path("ventes/facture/<int:facture_id>/pdf/", facture_pdf, name="facture-pdf"),
]
