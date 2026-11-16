from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("konto/login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("konto/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("konto/adgangskode/", auth_views.PasswordChangeView.as_view(), name="password_change"),
    path("konto/adgangskode/skiftet/", auth_views.PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("", include("workload.urls")),
]
