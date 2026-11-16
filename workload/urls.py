from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("uge/<int:year>/<int:week>/", views.week_view, name="week"),
    path("uge/<int:year>/<int:week>/rediger/", views.week_edit, name="week_edit"),
    path("kalender/", views.year_current, name="year_current"),
    path("kalender/<int:year>/", views.year_view, name="year"),
    path("brugere/", views.user_list, name="user_list"),
    path("brugere/ny/", views.user_create, name="user_create"),
    path("brugere/<int:pk>/", views.user_edit, name="user_edit"),
    path("brugere/<int:pk>/adgangskode/", views.user_password, name="user_password"),
]
