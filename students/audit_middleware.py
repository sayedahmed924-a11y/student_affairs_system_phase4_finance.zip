import logging
from contextvars import ContextVar

from django.db import DatabaseError

from .models import SystemAuditEvent

logger = logging.getLogger(__name__)
_AUDIT_CONTEXT = ContextVar("student_affairs_audit_context", default=None)


def current_audit_context():
    return _AUDIT_CONTEXT.get()


class SystemAuditMiddleware:
    """Expose authenticated request metadata to model signals and finalize audit status."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        context = None
        if user is not None and user.is_authenticated and user.is_active:
            context = {
                "user": user,
                "path": request.path[:500],
                "method": request.method,
                "ip_address": request.META.get("REMOTE_ADDR") or None,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
                "event_ids": [],
            }
        token = _AUDIT_CONTEXT.set(context)
        try:
            response = self.get_response(request)
            if context:
                try:
                    event_ids = context.get("event_ids", [])
                    if event_ids:
                        SystemAuditEvent.objects.filter(pk__in=event_ids).update(
                            status_code=response.status_code
                        )
                    elif (
                        request.method == "POST"
                        and request.path.startswith("/students/backups/")
                        and 200 <= response.status_code < 400
                    ):
                        SystemAuditEvent.objects.create(
                            user=user,
                            actor_username=user.get_username()[:150],
                            module="backups",
                            action="إنشاء نسخة احتياطية",
                            path=request.path[:500],
                            method=request.method,
                            status_code=response.status_code,
                            ip_address=context["ip_address"],
                            user_agent=context["user_agent"],
                        )
                except DatabaseError:
                    logger.exception("Could not finalize central system audit event")
            return response
        finally:
            _AUDIT_CONTEXT.reset(token)
