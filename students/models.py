from django.conf import settings
from django.db import models
from django.utils import timezone

class Student(models.Model):
    STATUS = [
        ("new", "مستجد"), ("continuing", "باقٍ"), ("graduated", "خريج"),
        ("withdrawn", "منسحب"), ("dismissed", "مفصول"), ("suspended", "موقوف"),
    ]
    university_id = models.CharField("الرقم الجامعي", max_length=40, unique=True, db_index=True)
    full_name = models.CharField("اسم الطالب", max_length=200, db_index=True)
    national_id = models.CharField("الرقم القومي", max_length=20, blank=True, db_index=True)
    nationality = models.CharField("الجنسية", max_length=80, blank=True, default="مصري")
    phone = models.CharField("الهاتف", max_length=30, blank=True)
    address = models.TextField("العنوان", blank=True)
    academic_year = models.CharField("الفرقة الدراسية", max_length=50, blank=True)
    department = models.CharField("القسم", max_length=100, blank=True)
    division = models.CharField("الشعبة", max_length=100, blank=True)
    study_status = models.CharField("الحالة الدراسية", max_length=20, choices=STATUS, default="new")
    notes = models.TextField("ملاحظات", blank=True)
    is_archived = models.BooleanField("مؤرشف", default=False)
    created_at = models.DateTimeField("تاريخ الإضافة", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        ordering = ["university_id"]
        verbose_name = "طالب"
        verbose_name_plural = "الطلاب"

    def __str__(self):
        return f"{self.university_id} - {self.full_name}"

class AuditLog(models.Model):
    ACTIONS = [("create", "إضافة"), ("update", "تعديل"), ("archive", "أرشفة"), ("restore", "استعادة")]
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="audit_logs")
    action = models.CharField("العملية", max_length=20, choices=ACTIONS)
    field_name = models.CharField("الحقل", max_length=100, blank=True)
    old_value = models.TextField("القيمة القديمة", blank=True)
    new_value = models.TextField("القيمة الجديدة", blank=True)
    reason = models.TextField("سبب التغيير")
    source_document = models.FileField("المستند المؤيد", upload_to="audit_docs/%Y/%m/", blank=True)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="student_audit_logs")
    created_at = models.DateTimeField("تاريخ ووقت العملية", default=timezone.now, db_index=True)
    batch_id = models.UUIDField("معرف عملية جماعية", null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل تعديل"
        verbose_name_plural = "سجل التعديلات"

class ImportBatch(models.Model):
    STATUS = [("preview", "بانتظار الاعتماد"), ("approved", "معتمد"), ("rejected", "مرفوض")]
    file = models.FileField(upload_to="imports/%Y/%m/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS, default="preview")
    reason = models.TextField(blank=True)
    preview_json = models.JSONField(default=list)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_imports")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]


class AcademicTerm(models.Model):
    SEMESTERS = [("first", "الفصل الدراسي الأول"), ("second", "الفصل الدراسي الثاني"), ("summer", "الفصل الصيفي")]
    name = models.CharField("اسم الفصل الدراسي", max_length=120)
    academic_year = models.CharField("العام الجامعي", max_length=20)
    semester = models.CharField("الفصل", max_length=10, choices=SEMESTERS)
    starts_on = models.DateField("تاريخ البداية", null=True, blank=True)
    ends_on = models.DateField("تاريخ النهاية", null=True, blank=True)
    is_active = models.BooleanField("فصل حالي", default=False)

    class Meta:
        ordering = ["-academic_year", "semester"]
        verbose_name = "فصل دراسي"
        verbose_name_plural = "الفصول الدراسية"
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "semester"], name="uniq_academic_year_semester")
        ]

    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class Course(models.Model):
    code = models.CharField("كود المادة", max_length=30, unique=True)
    name = models.CharField("اسم المادة", max_length=180)
    department = models.CharField("القسم", max_length=100, blank=True)
    level = models.CharField("الفرقة", max_length=50, blank=True)
    credit_hours = models.DecimalField("الساعات المعتمدة", max_digits=4, decimal_places=1, default=0)
    max_score = models.DecimalField("النهاية العظمى", max_digits=6, decimal_places=2, default=100)
    pass_score = models.DecimalField("درجة النجاح", max_digits=6, decimal_places=2, default=50)
    excellent_percent = models.DecimalField("حد الامتياز %", max_digits=5, decimal_places=2, default=85)
    very_good_percent = models.DecimalField("حد جيد جدًا %", max_digits=5, decimal_places=2, default=75)
    good_percent = models.DecimalField("حد جيد %", max_digits=5, decimal_places=2, default=65)
    is_active = models.BooleanField("مفعلة", default=True)

    class Meta:
        ordering = ["department", "level", "code"]
        verbose_name = "مادة دراسية"
        verbose_name_plural = "المواد الدراسية"

    def __str__(self):
        return f"{self.code} - {self.name}"


class StudentEnrollment(models.Model):
    STATUSES = [
        ("enrolled", "مقيد"),
        ("withdrawn", "منسحب"),
        ("suspended", "موقوف"),
        ("completed", "أنهى الفصل"),
    ]
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollments")
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="enrollments")
    level = models.CharField("الفرقة وقت القيد", max_length=50)
    department = models.CharField("القسم وقت القيد", max_length=100, blank=True)
    status = models.CharField("حالة القيد", max_length=15, choices=STATUSES, default="enrolled")
    registered_at = models.DateTimeField("تاريخ التسجيل", auto_now_add=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        ordering = ["-term__academic_year", "student__university_id"]
        verbose_name = "قيد فصل دراسي"
        verbose_name_plural = "قيود الفصول الدراسية"
        constraints = [
            models.UniqueConstraint(fields=["student", "term"], name="uniq_student_term_enrollment")
        ]

    def __str__(self):
        return f"{self.student} - {self.term}"


class CourseRegistration(models.Model):
    RESULT_STATUSES = [
        ("pending", "لم ترصد"),
        ("passed", "ناجح"),
        ("failed", "راسب"),
        ("withdrawn", "منسحب"),
        ("incomplete", "غير مكتمل"),
    ]
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.PROTECT, related_name="course_registrations")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="registrations")
    coursework_score = models.DecimalField("أعمال السنة", max_digits=6, decimal_places=2, null=True, blank=True)
    exam_score = models.DecimalField("درجة الامتحان", max_digits=6, decimal_places=2, null=True, blank=True)
    total_score = models.DecimalField("المجموع", max_digits=6, decimal_places=2, null=True, blank=True)
    grade = models.CharField("التقدير", max_length=30, blank=True)
    result_status = models.CharField("حالة النتيجة", max_length=15, choices=RESULT_STATUSES, default="pending")
    result_source = models.CharField("مصدر النتيجة/رقم القرار", max_length=180, blank=True)
    result_reason = models.TextField("سبب تعديل النتيجة", blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        ordering = ["course__code"]
        verbose_name = "تسجيل مادة"
        verbose_name_plural = "تسجيلات المواد"
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "course"], name="uniq_enrollment_course")
        ]

    def __str__(self):
        return f"{self.enrollment.student} - {self.course}"


class StudentAcademicEvent(models.Model):
    EVENT_TYPES = [
        ("warning", "إنذار"),
        ("failure", "رسوب"),
        ("withdrawal", "انسحاب"),
        ("reenrollment", "إعادة قيد"),
        ("transfer", "تحويل"),
        ("suspension", "وقف قيد"),
        ("decision", "قرار إداري"),
        ("other", "أخرى"),
    ]
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="academic_events")
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, null=True, blank=True)
    event_type = models.CharField("نوع الواقعة", max_length=20, choices=EVENT_TYPES)
    event_date = models.DateField("تاريخ الواقعة")
    details = models.TextField("التفاصيل")
    reason = models.TextField("السبب/السند")
    reference_number = models.CharField("رقم القرار أو المستند", max_length=100, blank=True)
    document = models.FileField("المستند المؤيد", upload_to="academic_docs/%Y/%m/", blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField("تاريخ التسجيل", auto_now_add=True)

    class Meta:
        ordering = ["-event_date", "-created_at"]
        verbose_name = "واقعة أكاديمية"
        verbose_name_plural = "الوقائع الأكاديمية"

    def __str__(self):
        return f"{self.student} - {self.get_event_type_display()}"


class StudentCharge(models.Model):
    """A financial obligation assigned to one student; never delete official charges."""
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="charges", verbose_name="الطالب")
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, null=True, blank=True,
                             related_name="charges", verbose_name="الفصل الدراسي")
    title = models.CharField("بيان الاستحقاق", max_length=180)
    amount = models.DecimalField("قيمة الاستحقاق", max_digits=12, decimal_places=2)
    due_date = models.DateField("تاريخ الاستحقاق", null=True, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="created_student_charges")
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    is_cancelled = models.BooleanField("ملغي", default=False)
    cancellation_reason = models.TextField("سبب الإلغاء", blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                     null=True, blank=True, related_name="cancelled_student_charges")
    cancelled_at = models.DateTimeField("تاريخ الإلغاء", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "استحقاق مالي"
        verbose_name_plural = "الاستحقاقات المالية"
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="student_charge_amount_positive")]

    def __str__(self):
        return f"{self.student} - {self.title}"

    @property
    def paid_amount(self):
        from django.db.models import Sum
        value = self.payments.filter(is_voided=False).aggregate(total=Sum("amount"))["total"]
        return value or 0

    @property
    def balance(self):
        return self.amount - self.paid_amount

    @property
    def payment_status(self):
        if self.is_cancelled:
            return "ملغي"
        if self.balance <= 0:
            return "مسدد بالكامل"
        if self.paid_amount > 0:
            return "مسدد جزئيًا"
        return "غير مسدد"


class PaymentReceipt(models.Model):
    METHODS = [("cash", "نقدي"), ("bank", "تحويل بنكي"), ("card", "بطاقة"), ("other", "أخرى")]
    charge = models.ForeignKey(StudentCharge, on_delete=models.PROTECT, related_name="payments", verbose_name="الاستحقاق")
    receipt_number = models.CharField("رقم الإيصال", max_length=60, unique=True)
    amount = models.DecimalField("المبلغ المدفوع", max_digits=12, decimal_places=2)
    method = models.CharField("طريقة الدفع", max_length=10, choices=METHODS, default="cash")
    reference = models.CharField("رقم مرجعي", max_length=120, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name="student_payment_receipts")
    received_at = models.DateTimeField("تاريخ ووقت السداد", default=timezone.now, db_index=True)
    is_voided = models.BooleanField("ملغي", default=False)
    void_reason = models.TextField("سبب الإلغاء", blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                  null=True, blank=True, related_name="voided_student_receipts")
    voided_at = models.DateTimeField("تاريخ إلغاء الإيصال", null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "إيصال سداد"
        verbose_name_plural = "إيصالات السداد"
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_receipt_amount_positive")]

    def __str__(self):
        return self.receipt_number
