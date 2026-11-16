"""The two roles: admins (is_staff or superuser) and viewers (everyone else)."""

from functools import wraps

from django.core.exceptions import PermissionDenied


def is_admin(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and (user.is_staff or user.is_superuser)
    )


def admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def can_manage(actor, target) -> bool:
    """Admins manage users, but only a superuser may touch a superuser account."""
    return is_admin(actor) and (actor.is_superuser or not target.is_superuser)
