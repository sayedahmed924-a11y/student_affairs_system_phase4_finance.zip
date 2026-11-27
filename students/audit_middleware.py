import logging
import re

from .models import SystemAuditEvent

logger = logging.getLogger(__name__)
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_OBJECT_ID = re.compile(r"(?:^|/)(\d+)(?:/|$)")


def _module_for_path(path):
    if path.startswith("/students/finance/"):
        return "finance", "الإدارة المالية"
    if path.startswith("/students/academic/") or path.endswith("/transcript/"):
        return "academic", "الشؤون الأكاديمية"
    if path.startswith("/students/import/"):
        return "imports", "استيراد البيانات"
    if path.startswith("/students/backups/"):
        return "backups", "النسخ الاحتياطي"
    if path.startswith("/students/staff-access/"):
        return "users", "المستخدمون والصلاحيات"
    if path.startswith("/students/"):
        return "students", "شؤون الطلاب"
    return "system", "النظام"


def _action_for_request(path, method):
    lowered = path.rstrip("/").lower()
    if method == "DELETE" or any(x in lowered for x in ("/void", "/cancel", "/reject")):
        return "إلغاء أو رفض سجل"
    if "/approve" in lowered:
        return "اعتماد بيانات"
    if method == "POST" and any(x in lowered for x in ("/add", "/create", "/payments")):
        return "إضافة سجل"
    if method in {"PUT", "PATCH"} or "/edit" in lowered:
        return "تعديل بيانات"
    if "/import/" in lowered:
        return "استيراد أو معالجة ملف"
    if "/backups/" in lowered:
        return "إنشاء نسخة احتياطية"
    if "/staff-access/" in lowered:
        return "إدارة حساب أو صلاحية"
    return "تنفيذ إجراء"


class SystemAuditMiddleware:
    """Record successful authenticated write requests without storing submitted form data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            user = getattr(request, "user", None)
            if (
                request.method in _WRITE_METHODS
                and 200 <= response.status_code < 400
                and user is not None
                and user.is_authenticated
                and user.is_active
                and not request.path.startswith("/static/")
            ):
                module, _ = _module_for_path(request.path)
                object_ids = _OBJECT_ID.findall(request.path)
                object_reference = object_ids[-1] if object_ids else ""
                SystemAuditEvent.objects.create(
                    user=user,
                    actor_username=user.get_username()[:150],
                    module=module,
                    action=_action_for_request(request.path, request.method),
                    path=request.path[:500],
                    object_reference=object_reference[:120],
                    method=request.method,
                    status_code=response.status_code,
                    ip_address=request.META.get("REMOTE_ADDR") or None,
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                )
        except Exception:
            # Audit storage failure must not turn a completed student/finance operation into an HTTP error.
            logger.exception("Could not write system audit event")
        return response
