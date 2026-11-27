from django.contrib import admin
from .models import Student, AuditLog, ImportBatch

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("university_id", "full_name", "academic_year", "department", "study_status", "is_archived")
    search_fields = ("university_id", "full_name", "national_id")
    list_filter = ("academic_year", "department", "study_status", "is_archived")

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("student", "action", "field_name", "employee", "created_at")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "uploaded_by", "uploaded_at", "status", "approved_by")


from .models import AcademicTerm, Course, StudentEnrollment, CourseRegistration, StudentAcademicEvent

@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "semester", "is_active")
    list_filter = ("academic_year", "semester", "is_active")

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "department", "level", "credit_hours", "is_active")
    search_fields = ("code", "name")
    list_filter = ("department", "level", "is_active")

@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "term", "level", "department", "status")
    search_fields = ("student__university_id", "student__full_name")
    list_filter = ("term", "level", "status")

@admin.register(CourseRegistration)
class CourseRegistrationAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "course", "total_score", "grade", "result_status", "updated_by")
    search_fields = ("enrollment__student__university_id", "enrollment__student__full_name", "course__name")
    list_filter = ("result_status", "course")

    def save_model(self, request, obj, form, change):
        old_values = {}
        if change:
            previous = CourseRegistration.objects.get(pk=obj.pk)
            for field in ("coursework_score", "exam_score", "total_score", "grade",
                          "result_status", "result_source"):
                old_values[field] = str(getattr(previous, field) or "")
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        for field in ("coursework_score", "exam_score", "total_score", "grade",
                      "result_status", "result_source"):
            new_value = str(getattr(obj, field) or "")
            old_value = old_values.get(field, "")
            if old_value != new_value:
                AuditLog.objects.create(
                    student=obj.enrollment.student, action="update",
                    field_name=f"نتيجة {obj.course.code} - {field}",
                    old_value=old_value, new_value=new_value,
                    reason=obj.result_reason or "تعديل نتيجة من لوحة الإدارة",
                    employee=request.user)

@admin.register(StudentAcademicEvent)
class StudentAcademicEventAdmin(admin.ModelAdmin):
    list_display = ("student", "event_type", "event_date", "term", "recorded_by")
    search_fields = ("student__university_id", "student__full_name", "reference_number")
    list_filter = ("event_type", "term")
    readonly_fields = ("recorded_by", "created_at")


# Academic events are formal records; create them through the audited application form.
# Existing event records are read-only in admin and are never hard-deleted.
StudentAcademicEventAdmin.readonly_fields = [f.name for f in StudentAcademicEvent._meta.fields]
StudentAcademicEventAdmin.has_change_permission = lambda self, request, obj=None: False
StudentAcademicEventAdmin.has_delete_permission = lambda self, request, obj=None: False


from .models import StudentCharge, PaymentReceipt

@admin.register(StudentCharge)
class StudentChargeAdmin(admin.ModelAdmin):
    list_display = ("student", "title", "amount", "term", "is_cancelled", "created_by", "created_at")
    search_fields = ("student__university_id", "student__full_name", "title")
    readonly_fields = [f.name for f in StudentCharge._meta.fields]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

@admin.register(PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "charge", "amount", "method", "received_by", "received_at", "is_voided")
    search_fields = ("receipt_number", "charge__student__university_id", "charge__student__full_name")
    readonly_fields = [f.name for f in PaymentReceipt._meta.fields]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


from .models import SystemAuditEvent

@admin.register(SystemAuditEvent)
class SystemAuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_username", "module", "action", "method", "status_code", "ip_address")
    list_filter = ("module", "method", "status_code", "created_at")
    search_fields = ("actor_username", "action", "path", "object_reference", "ip_address")
    readonly_fields = [field.name for field in SystemAuditEvent._meta.fields]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from .models import FeeCatalog, SupplyOrder, SupplyOrderLine

@admin.register(FeeCatalog)
class FeeCatalogAdmin(admin.ModelAdmin):
    list_display = ("category", "name", "amount", "currency", "bank_name", "is_active", "updated_at")
    list_filter = ("category", "currency", "is_active")
    search_fields = ("name", "bank_name", "source_workbook", "source_sheet")
    readonly_fields = ("updated_at",)

@admin.register(SupplyOrder)
class SupplyOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "category", "total_amount", "currency", "bank_name", "source_workbook", "imported_at")
    list_filter = ("category", "currency", "imported_at")
    search_fields = ("order_number", "bank_name", "source_workbook")
    readonly_fields = [field.name for field in SupplyOrder._meta.fields]

@admin.register(SupplyOrderLine)
class SupplyOrderLineAdmin(admin.ModelAdmin):
    list_display = ("order", "student", "service_name", "amount", "currency", "source_row")
    search_fields = ("student__university_id", "student__full_name", "service_name", "order__order_number")
    readonly_fields = [field.name for field in SupplyOrderLine._meta.fields]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
