import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .audit_middleware import current_audit_context
from .models import (
    AcademicTerm, Course, CourseRegistration, ImportBatch, PaymentReceipt,
    Student, StudentAcademicEvent, StudentCharge, StudentEnrollment,
    SystemAuditEvent,
)

logger = logging.getLogger(__name__)
User = get_user_model()

MODEL_MODULES = {
    Student: "students",
    ImportBatch: "imports",
    AcademicTerm: "academic",
    Course: "academic",
    StudentEnrollment: "academic",
    CourseRegistration: "academic",
    StudentAcademicEvent: "academic",
    StudentCharge: "finance",
    PaymentReceipt: "finance",
    User: "users",
}


def _queue_event(instance, action):
    context = current_audit_context()
    if not context:
        return
    user = context.get("user")
    if not user or not user.is_authenticated or not user.is_active:
        return

    module = MODEL_MODULES.get(type(instance), "system")
    label = str(getattr(instance._meta, "verbose_name", instance.__class__.__name__))
    payload = {
        "user": user,
        "actor_username": user.get_username()[:150],
        "module": module,
        "action": f"{action}: {label}"[:100],
        "path": context.get("path", "")[:500],
        "object_reference": str(instance.pk or "")[:120],
        "method": context.get("method", "")[:10],
        "ip_address": context.get("ip_address"),
        "user_agent": context.get("user_agent", "")[:500],
    }

    def write_after_commit():
        try:
            event = SystemAuditEvent.objects.create(**payload)
            context.setdefault("event_ids", []).append(event.pk)
        except Exception:
            logger.exception("Could not persist model audit event")

    transaction.on_commit(write_after_commit)


@receiver(post_save, dispatch_uid="students_central_audit_post_save")
def audit_model_save(sender, instance, created, raw=False, **kwargs):
    if raw or sender is SystemAuditEvent or sender not in MODEL_MODULES:
        return
    _queue_event(instance, "إضافة" if created else "تعديل")


@receiver(post_delete, dispatch_uid="students_central_audit_post_delete")
def audit_model_delete(sender, instance, **kwargs):
    if sender is SystemAuditEvent or sender not in MODEL_MODULES:
        return
    _queue_event(instance, "حذف")
