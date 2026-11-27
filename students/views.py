import json, uuid
from datetime import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from openpyxl import load_workbook
from .models import Student, AuditLog, ImportBatch
from .forms import StudentForm, ImportForm, StudentChargeForm, PaymentReceiptForm, VoidReceiptForm
from .models import StudentCharge, PaymentReceipt

@login_required
@permission_required("students.view_student", raise_exception=True)
def dashboard(request):
    active_students = Student.objects.filter(is_archived=False)
    total = active_students.count()
    status_stats = []
    for value, label in Student.STATUS:
        count = active_students.filter(study_status=value).count()
        status_stats.append({
            "label": label,
            "count": count,
            "percent": round((count * 100 / total), 1) if total else 0,
        })
    return render(request, "students/dashboard.html", {
        "total": total,
        "new_count": active_students.filter(study_status="new").count(),
        "pending": ImportBatch.objects.filter(status="preview").count(),
        "recent": AuditLog.objects.select_related("student", "employee")[:8] if request.user.has_perm("students.view_auditlog") else [],
        "status_stats": status_stats,
    })

@login_required
@permission_required("students.view_student", raise_exception=True)
def student_list(request):
    q = request.GET.get("q", "").strip()
    students = Student.objects.filter(is_archived=False)
    if q:
        students = students.filter(Q(university_id__icontains=q) | Q(full_name__icontains=q) | Q(national_id__icontains=q))
    return render(request, "students/student_list.html", {"students": students[:300], "q": q})

@login_required
@permission_required("students.view_student", raise_exception=True)
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    logs = student.audit_logs.select_related("employee") if request.user.has_perm("students.view_auditlog") else AuditLog.objects.none()
    return render(request, "students/student_detail.html", {"student": student, "logs": logs})

def _log_changes(student, old, new, user, reason, document=None, action="update", batch_id=None):
    for field, value in new.items():
        previous = old.get(field, "")
        if str(previous) != str(value):
            AuditLog.objects.create(student=student, action=action, field_name=field,
                old_value=str(previous or ""), new_value=str(value or ""), reason=reason,
                employee=user, source_document=document or "", batch_id=batch_id)

@login_required
@permission_required("students.add_student", raise_exception=True)
def student_add(request):
    if request.method == "POST":
        form = StudentForm(request.POST, request.FILES)
        if form.is_valid():
            student = form.save(commit=False)
            student.save()
            values = {f.name: str(getattr(student, f.name) or "") for f in Student._meta.fields}
            AuditLog.objects.create(student=student, action="create", field_name="",
                old_value="", new_value=json.dumps(values, ensure_ascii=False),
                reason=form.cleaned_data["reason"], employee=request.user,
                source_document=form.cleaned_data.get("source_document") or "")
            messages.success(request, "تمت إضافة الطالب وتسجيل العملية.")
            return redirect("students:detail", pk=student.pk)
    else:
        form = StudentForm()
    return render(request, "students/student_form.html", {"form": form, "title": "إضافة طالب جديد"})

@login_required
@permission_required("students.change_student", raise_exception=True)
def student_edit(request, pk):
    if request.method == "POST":
        with transaction.atomic():
            student = get_object_or_404(Student.objects.select_for_update(), pk=pk)
            form = StudentForm(request.POST, request.FILES, instance=student)
            if form.is_valid():
                submitted_version = parse_datetime(form.cleaned_data.get("version_token", ""))
                if not submitted_version or submitted_version != student.updated_at:
                    form.add_error(None, "تم تعديل بيانات هذا الطالب بواسطة موظف آخر بعد فتح الصفحة. لم يتم حفظ بياناتك؛ أعد تحميل الصفحة وراجع التعديلات الحالية.")
                else:
                    reason = form.cleaned_data["reason"]
                    doc = form.cleaned_data.get("source_document")
                    old = {f.name: getattr(student, f.name) for f in Student._meta.fields}
                    updated = form.save(commit=False)
                    updated.save()
                    new = {f.name: getattr(updated, f.name) for f in Student._meta.fields}
                    changes = {k: v for k, v in new.items() if str(old.get(k) or "") != str(v or "")}
                    _log_changes(updated, old, changes, request.user, reason, doc)
                    messages.success(request, "تم حفظ التعديلات وتوثيقها.")
                    return redirect("students:detail", pk=updated.pk)
    else:
        student = get_object_or_404(Student, pk=pk)
        form = StudentForm(instance=student, initial={"version_token": student.updated_at.isoformat()})
    return render(request, "students/student_form.html", {"form": form, "title": "تعديل بيانات الطالب"})

@login_required
@permission_required("students.view_auditlog", raise_exception=True)
def audit_list(request):
    logs = AuditLog.objects.select_related("student", "employee")[:500]
    return render(request, "students/audit_list.html", {"logs": logs})

@login_required
@permission_required("students.add_importbatch", raise_exception=True)
def import_preview(request):
    if request.method == "POST":
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            if not uploaded.name.lower().endswith(".xlsx"):
                form.add_error("file", "يرجى رفع ملف بصيغة XLSX.")
            else:
                wb = load_workbook(uploaded, read_only=True, data_only=True)
                ws = wb.active
                rows = list(ws.iter_rows(values_only=True))
                headers = [str(x).strip() if x is not None else "" for x in rows[0]]
                required = ["university_id", "full_name"]
                if not all(x in headers for x in required):
                    form.add_error("file", "يجب أن يحتوي الصف الأول على university_id و full_name على الأقل.")
                else:
                    preview, seen, errors = [], set(), []
                    for line, row in enumerate(rows[1:], start=2):
                        data = dict(zip(headers, row))
                        uid = str(data.get("university_id") or "").strip()
                        if not uid:
                            errors.append({"row": line, "error": "الرقم الجامعي فارغ"})
                            continue
                        if uid in seen:
                            errors.append({"row": line, "error": f"تكرار الرقم الجامعي داخل الملف: {uid}"})
                            continue
                        seen.add(uid)
                        existing = Student.objects.filter(university_id=uid).first()
                        allowed = ["full_name","national_id","nationality","phone","address","academic_year","department","division","study_status","notes"]
                        changes = {}
                        for field in allowed:
                            if field in data and data[field] is not None:
                                val = str(data[field]).strip()
                                oldval = str(getattr(existing, field) or "") if existing else ""
                                if val != oldval:
                                    changes[field] = {"old": oldval, "new": val}
                        preview.append({"row": line, "university_id": uid,
                            "operation": "update" if existing else "create",
                            "changes": changes, "full_name": str(data.get("full_name") or "")})
                    batch = ImportBatch.objects.create(file=uploaded, uploaded_by=request.user,
                        reason=form.cleaned_data["reason"], preview_json={"items": preview, "errors": errors})
                    return render(request, "students/import_preview.html", {"batch": batch, "preview": preview, "errors": errors})
    else:
        form = ImportForm()
    return render(request, "students/import_form.html", {"form": form})

@login_required
@permission_required("students.change_importbatch", raise_exception=True)
def import_approve(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk, status="preview")
    if request.method != "POST":
        return redirect("students:import_preview")
    payload = batch.preview_json
    if not isinstance(payload, dict):
        messages.error(request, "بيانات المعاينة غير صالحة.")
        return redirect("students:import_preview")
    items = payload.get("items", [])
    batch_id = uuid.uuid4()
    try:
        with transaction.atomic():
            for item in items:
                student = Student.objects.select_for_update().filter(
                    university_id=item["university_id"]).first()
                creating = student is None
                if creating:
                    student = Student(university_id=item["university_id"],
                                      full_name=item.get("full_name", "") or "غير محدد")
                old = {f.name: getattr(student, f.name) for f in Student._meta.fields}
                # Reject a stale preview rather than silently overwriting changes made meanwhile.
                if not creating:
                    for field, change in item.get("changes", {}).items():
                        current = str(getattr(student, field) or "")
                        if current != str(change.get("old") or ""):
                            raise ValueError(
                                f"تغيرت بيانات الطالب {student.university_id} بعد المعاينة؛ أعد رفع الملف.")
                for field, change in item.get("changes", {}).items():
                    setattr(student, field, change["new"])
                if creating and not student.full_name:
                    student.full_name = item.get("full_name", "غير محدد")
                student.save()
                if creating:
                    AuditLog.objects.create(student=student, action="create", new_value="إنشاء عبر Excel",
                        reason=batch.reason, employee=request.user, batch_id=batch_id)
                else:
                    changes = {k: getattr(student, k) for k in item.get("changes", {})}
                    _log_changes(student, old, changes, request.user, batch.reason, batch_id=batch_id)
            batch.status = "approved"
            batch.approved_by = request.user
            batch.approved_at = timezone.now()
            batch.save()
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("students:import_preview")
    messages.success(request, "تم اعتماد التحديث الجماعي.")
    return redirect("students:dashboard")

@login_required
@permission_required("students.change_importbatch", raise_exception=True)
def import_reject(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk, status="preview")
    if request.method == "POST":
        batch.status = "rejected"
        batch.approved_by = request.user
        batch.approved_at = timezone.now()
        batch.save()
        messages.info(request, "تم رفض دفعة التحديث.")
    return redirect("students:dashboard")


from .models import AcademicTerm, Course, StudentEnrollment, CourseRegistration, StudentAcademicEvent
from .forms import AcademicTermForm, CourseForm, EnrollmentForm, CourseRegistrationForm, AcademicEventForm, ReEnrollmentForm

@login_required
@permission_required("students.view_academicterm", raise_exception=True)
def academic_home(request):
    return render(request, "students/academic_home.html", {
        "terms": AcademicTerm.objects.all()[:10],
        "courses_count": Course.objects.count(),
        "enrollments_count": StudentEnrollment.objects.count(),
        "results_count": CourseRegistration.objects.count(),
        "events_count": StudentAcademicEvent.objects.count(),
    })

@login_required
@permission_required("students.view_academicterm", raise_exception=True)
def term_list(request):
    return render(request, "students/term_list.html", {"items": AcademicTerm.objects.all()})

@login_required
@permission_required("students.add_academicterm", raise_exception=True)
def term_add(request):
    form = AcademicTermForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        term = form.save()
        messages.success(request, "تمت إضافة الفصل الدراسي.")
        return redirect("students:academic")
    return render(request, "students/simple_form.html", {"form": form, "title": "إضافة فصل دراسي"})

@login_required
@permission_required("students.view_course", raise_exception=True)
def course_list(request):
    return render(request, "students/course_list.html", {"items": Course.objects.all()})

@login_required
@permission_required("students.add_course", raise_exception=True)
def course_add(request):
    form = CourseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        course = form.save()
        matching = StudentEnrollment.objects.filter(status="enrolled")
        if course.level:
            matching = matching.filter(Q(level="") | Q(level=course.level))
        if course.department:
            matching = matching.filter(department=course.department)
        with transaction.atomic():
            for enrollment in matching:
                CourseRegistration.objects.get_or_create(enrollment=enrollment, course=course)
        messages.success(request, "تمت إضافة المادة وربطها تلقائيًا بقيود الطلاب المطابقة.")
        return redirect("students:courses")
    return render(request, "students/simple_form.html", {"form": form, "title": "إضافة مادة دراسية"})

@login_required
@permission_required("students.view_studentenrollment", raise_exception=True)
def enrollment_list(request):
    return render(request, "students/enrollment_list.html", {
        "items": StudentEnrollment.objects.select_related("student", "term")[:500]
    })

@login_required
@permission_required("students.add_studentenrollment", raise_exception=True)
def enrollment_add(request):
    form = EnrollmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            enrollment = form.save()
            courses = Course.objects.filter(is_active=True).filter(Q(level="") | Q(level=enrollment.level))
            courses = courses.filter(Q(department="") | Q(department=enrollment.department)) if enrollment.department else courses.filter(department="")
            if enrollment.status != "enrolled":
                courses = Course.objects.none()
            created = 0
            for course in courses:
                _, was_created = CourseRegistration.objects.get_or_create(enrollment=enrollment, course=course)
                created += int(was_created)
            AuditLog.objects.create(student=enrollment.student, action="update",
                field_name="قيد فصل دراسي", old_value="", new_value=str(enrollment.term),
                reason="إنشاء قيد وتسجيل المواد المطابقة تلقائيًا", employee=request.user)
        messages.success(request, f"تم تسجيل القيد وإضافة {created} مادة مطابقة تلقائيًا.")
        return redirect("students:transcript", pk=enrollment.student_id)
    return render(request, "students/simple_form.html", {"form": form, "title": "تسجيل قيد فصل دراسي"})

@login_required
@permission_required("students.view_courseregistration", raise_exception=True)
def result_list(request):
    return render(request, "students/result_list.html", {
        "items": CourseRegistration.objects.select_related("enrollment__student", "enrollment__term", "course")[:500]
    })

@login_required
@permission_required("students.add_courseregistration", raise_exception=True)
def result_add(request):
    form = CourseRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        candidate = form.save(commit=False)
        existing = CourseRegistration.objects.filter(enrollment=candidate.enrollment, course=candidate.course).first()
        if existing:
            old_value = f"{existing.coursework_score} / {existing.exam_score} / {existing.total_score} / {existing.grade} / {existing.result_status}"
            obj = existing
            for field in ("coursework_score", "exam_score", "grade", "result_source", "result_reason"):
                setattr(obj, field, getattr(candidate, field))
        else:
            obj = candidate
            old_value = "لا توجد نتيجة مرصودة"
        if obj.coursework_score is not None and obj.exam_score is not None:
            obj.total_score = obj.coursework_score + obj.exam_score
            if obj.total_score > obj.course.max_score:
                form.add_error(None, f"المجموع تجاوز النهاية العظمى للمادة ({obj.course.max_score}).")
            else:
                percentage = (obj.total_score / obj.course.max_score) * 100 if obj.course.max_score else 0
                obj.result_status = "passed" if obj.total_score >= obj.course.pass_score else "failed"
                if obj.result_status == "failed": obj.grade = "راسب"
                elif percentage >= obj.course.excellent_percent: obj.grade = "ممتاز"
                elif percentage >= obj.course.very_good_percent: obj.grade = "جيد جدًا"
                elif percentage >= obj.course.good_percent: obj.grade = "جيد"
                else: obj.grade = "مقبول"
        else:
            obj.total_score = None
            obj.result_status = "pending"
            obj.grade = ""
        if form.errors:
            return render(request, "students/simple_form.html", {"form": form, "title": "إضافة/رصد نتيجة مادة"})
        obj.updated_by = request.user
        obj.save()
        new_value = f"{obj.coursework_score} / {obj.exam_score} / {obj.total_score} / {obj.grade} / {obj.result_status}"
        AuditLog.objects.create(student=obj.enrollment.student, action="update",
            field_name=f"رصد نتيجة مادة {obj.course.code}", old_value=old_value,
            new_value=new_value, reason=obj.result_reason or "إضافة/تحديث نتيجة", employee=request.user)
        messages.success(request, "تم حفظ النتيجة وتحديث المجموع والتقدير وحالة النجاح/الرسوب.")
        return redirect("students:transcript", pk=obj.enrollment.student_id)
    return render(request, "students/simple_form.html", {"form": form, "title": "إضافة/رصد نتيجة مادة"})

@login_required
@permission_required("students.view_studentacademicevent", raise_exception=True)
def event_list(request):
    return render(request, "students/event_list.html", {
        "items": StudentAcademicEvent.objects.select_related("student", "term", "recorded_by")[:500]
    })

@login_required
@permission_required("students.add_studentacademicevent", raise_exception=True)
def event_add(request):
    form = AcademicEventForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.recorded_by = request.user
        obj.save()
        AuditLog.objects.create(student=obj.student, action="update",
            field_name=obj.get_event_type_display(), old_value="",
            new_value=obj.details, reason=obj.reason, employee=request.user,
            source_document=obj.document.name if obj.document else "")
        messages.success(request, "تم تسجيل الواقعة الأكاديمية.")
        return redirect("students:events")
    return render(request, "students/simple_form.html", {"form": form, "title": "إضافة واقعة أكاديمية"})


@login_required
@permission_required("students.view_student", raise_exception=True)
@permission_required("students.view_courseregistration", raise_exception=True)
def student_transcript(request, pk):
    student = get_object_or_404(Student, pk=pk)
    enrollments = StudentEnrollment.objects.filter(student=student).select_related("term").prefetch_related("course_registrations__course")
    rows = []
    from decimal import Decimal
    earned_by_course = {}
    required_by_course = {}
    attempted_hours = Decimal("0")
    for enrollment in enrollments:
        for registration in enrollment.course_registrations.all():
            attempted_hours += registration.course.credit_hours
            if registration.result_status == "passed":
                earned_by_course[registration.course_id] = registration.course.credit_hours
            rows.append(registration)
    catalog = Course.objects.filter(is_active=True)
    if student.department:
        catalog = catalog.filter(Q(department="") | Q(department=student.department))
    else:
        catalog = catalog.filter(department="")
    for course in catalog:
        required_by_course[course.pk] = course.credit_hours
    earned_hours = sum(earned_by_course.values(), Decimal("0"))
    required_hours = sum(required_by_course.values(), Decimal("0"))
    remaining_hours = max(required_hours - earned_hours, Decimal("0"))
    return render(request, "students/student_transcript.html", {
        "student": student, "enrollments": enrollments, "rows": rows,
        "earned_hours": earned_hours, "attempted_hours": attempted_hours,
        "required_hours": required_hours, "remaining_hours": remaining_hours,
    })

@login_required
@permission_required("students.add_studentenrollment", raise_exception=True)
def reenrollment_add(request):
    form = ReEnrollmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            enrollment, created = StudentEnrollment.objects.get_or_create(
                student=data["student"], term=data["term"],
                defaults={"level": data["level"], "department": data["department"], "status": "enrolled",
                          "notes": "إعادة قيد: " + data["reason"]})
            if not created:
                form.add_error("term", "يوجد قيد مسجل لهذا الطالب في الفصل المختار بالفعل.")
                return render(request, "students/simple_form.html", {"form": form, "title": "إعادة قيد طالب"})
            matches = Course.objects.filter(is_active=True).filter(Q(level="") | Q(level=enrollment.level))
            matches = matches.filter(Q(department="") | Q(department=enrollment.department)) if enrollment.department else matches.filter(department="")
            for course in matches:
                CourseRegistration.objects.get_or_create(enrollment=enrollment, course=course)
            StudentAcademicEvent.objects.create(student=data["student"], term=data["term"],
                event_type="reenrollment", event_date=timezone.localdate(),
                details="إعادة قيد الطالب في " + str(data["term"]), reason=data["reason"],
                reference_number=data["reference_number"], recorded_by=request.user)
            AuditLog.objects.create(student=data["student"], action="update",
                field_name="إعادة قيد", old_value="", new_value=str(data["term"]),
                reason=data["reason"], employee=request.user)
        messages.success(request, "تمت إعادة القيد مع الاحتفاظ بالقيود السابقة وتسجيل المواد المناسبة.")
        return redirect("students:transcript", pk=data["student"].pk)
    return render(request, "students/simple_form.html", {"form": form, "title": "إعادة قيد طالب"})


@login_required
@permission_required("students.change_courseregistration", raise_exception=True)
def result_edit(request, pk):
    registration = get_object_or_404(CourseRegistration.objects.select_related("course", "enrollment__student"), pk=pk)
    form = CourseRegistrationForm(request.POST or None, instance=registration)
    if request.method == "POST" and form.is_valid():
        previous = CourseRegistration.objects.get(pk=pk)
        old_value = f"{previous.coursework_score} / {previous.exam_score} / {previous.total_score} / {previous.grade} / {previous.result_status}"
        updated = form.save(commit=False)
        if updated.coursework_score is not None and updated.exam_score is not None:
            updated.total_score = updated.coursework_score + updated.exam_score
            if updated.total_score > updated.course.max_score:
                form.add_error(None, f"المجموع تجاوز النهاية العظمى للمادة ({updated.course.max_score}).")
            else:
                percentage = updated.total_score / updated.course.max_score * 100 if updated.course.max_score else 0
                updated.result_status = "passed" if updated.total_score >= updated.course.pass_score else "failed"
                if updated.result_status == "failed": updated.grade = "راسب"
                elif percentage >= updated.course.excellent_percent: updated.grade = "ممتاز"
                elif percentage >= updated.course.very_good_percent: updated.grade = "جيد جدًا"
                elif percentage >= updated.course.good_percent: updated.grade = "جيد"
                else: updated.grade = "مقبول"
        else:
            updated.total_score = None
            updated.result_status = "pending"
            updated.grade = ""
        if form.errors:
            return render(request, "students/simple_form.html", {"form": form, "title": "تعديل نتيجة مادة"})
        updated.updated_by = request.user
        updated.save()
        new_value = f"{updated.coursework_score} / {updated.exam_score} / {updated.total_score} / {updated.grade} / {updated.result_status}"
        AuditLog.objects.create(student=updated.enrollment.student, action="update",
            field_name=f"تعديل نتيجة مادة {updated.course.code}", old_value=old_value,
            new_value=new_value, reason=updated.result_reason or "تعديل نتيجة", employee=request.user)
        messages.success(request, "تم تعديل النتيجة وتسجيل القيمة السابقة والجديدة في سجل التعديلات.")
        return redirect("students:transcript", pk=updated.enrollment.student_id)
    return render(request, "students/simple_form.html", {"form": form, "title": "تعديل نتيجة مادة"})


@login_required
@permission_required("students.view_studentcharge", raise_exception=True)
@permission_required("students.view_paymentreceipt", raise_exception=True)
def finance_home(request):
    from django.db.models import Sum
    charges = StudentCharge.objects.filter(is_cancelled=False).prefetch_related("payments")
    total_due = charges.aggregate(total=Sum("amount"))["total"] or 0
    total_paid = PaymentReceipt.objects.filter(is_voided=False, charge__is_cancelled=False).aggregate(total=Sum("amount"))["total"] or 0
    total_balance = total_due - total_paid
    return render(request, "students/finance_home.html", {
        "charges_count": charges.count(), "receipts_count": PaymentReceipt.objects.filter(is_voided=False).count(),
        "total_due": total_due, "total_paid": total_paid, "total_balance": total_balance,
        "recent_receipts": PaymentReceipt.objects.select_related("charge__student", "received_by")[:10],
    })


@login_required
@permission_required("students.add_studentcharge", raise_exception=True)
def charge_add(request):
    form = StudentChargeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        charge = form.save(commit=False)
        charge.created_by = request.user
        charge.save()
        messages.success(request, "تم تسجيل الاستحقاق المالي.")
        return redirect("students:finance_charges")
    return render(request, "students/simple_form.html", {"form": form, "title": "إضافة استحقاق مالي"})


@login_required
@permission_required("students.view_studentcharge", raise_exception=True)
@permission_required("students.view_paymentreceipt", raise_exception=True)
def finance_charges(request):
    q = request.GET.get("q", "").strip()
    charges = StudentCharge.objects.select_related("student", "term", "created_by").prefetch_related("payments")
    if q:
        charges = charges.filter(Q(student__university_id__icontains=q) | Q(student__full_name__icontains=q) | Q(title__icontains=q))
    return render(request, "students/finance_charges.html", {"charges": charges[:500], "q": q})


@login_required
@permission_required("students.add_paymentreceipt", raise_exception=True)
def payment_add(request):
    form = PaymentReceiptForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            with transaction.atomic():
                charge = StudentCharge.objects.select_for_update().get(pk=data["charge"].pk)
                if charge.is_cancelled:
                    raise ValueError("لا يمكن السداد على استحقاق ملغي.")
                from django.db.models import Sum
                paid = charge.payments.filter(is_voided=False).aggregate(total=Sum("amount"))["total"] or 0
                if data["amount"] > charge.amount - paid:
                    raise ValueError("المبلغ أكبر من الرصيد المتبقي على هذا الاستحقاق.")
                receipt = form.save(commit=False)
                receipt.charge = charge
                receipt.received_by = request.user
                receipt.save()
        except ValueError as exc:
            form.add_error(None, str(exc))
        except IntegrityError:
            if PaymentReceipt.objects.filter(receipt_number=data["receipt_number"]).exists():
                form.add_error("receipt_number", "رقم الإيصال مستخدم من قبل؛ لم يتم تسجيل إيصال مكرر.")
            else:
                raise
        else:
            messages.success(request, f"تم تسجيل السداد. رقم الإيصال: {receipt.receipt_number}")
            return redirect("students:receipt_list")
    return render(request, "students/simple_form.html", {"form": form, "title": "تسجيل سداد وإصدار إيصال"})


@login_required
@permission_required("students.view_paymentreceipt", raise_exception=True)
def receipt_list(request):
    q = request.GET.get("q", "").strip()
    receipts = PaymentReceipt.objects.select_related("charge__student", "received_by", "voided_by")
    if q:
        receipts = receipts.filter(Q(receipt_number__icontains=q) | Q(charge__student__university_id__icontains=q) | Q(charge__student__full_name__icontains=q))
    return render(request, "students/receipt_list.html", {"receipts": receipts[:500], "q": q})


@login_required
@permission_required("students.change_paymentreceipt", raise_exception=True)
def receipt_void(request, pk):
    receipt = get_object_or_404(PaymentReceipt.objects.select_related("charge"), pk=pk)
    if request.method != "POST":
        return redirect("students:receipt_list")
    form = VoidReceiptForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            # Keep the same lock order as payment_add: charge first, then receipt.
            charge_id = PaymentReceipt.objects.only("charge_id").get(pk=pk).charge_id
            StudentCharge.objects.select_for_update().get(pk=charge_id)
            receipt = PaymentReceipt.objects.select_for_update().get(pk=pk)
            if receipt.is_voided:
                messages.warning(request, "الإيصال ملغي بالفعل.")
            else:
                receipt.is_voided = True
                receipt.void_reason = form.cleaned_data["reason"]
                receipt.voided_by = request.user
                receipt.voided_at = timezone.now()
                receipt.save(update_fields=["is_voided", "void_reason", "voided_by", "voided_at"])
                messages.success(request, "تم إلغاء الإيصال مع الاحتفاظ بسجله.")
    else:
        messages.error(request, "يجب كتابة سبب إلغاء الإيصال.")
    return redirect("students:receipt_list")


@login_required
@permission_required("students.change_studentcharge", raise_exception=True)
def charge_cancel(request, pk):
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        with transaction.atomic():
            charge = get_object_or_404(StudentCharge.objects.select_for_update(), pk=pk)
            if not reason:
                messages.error(request, "يجب كتابة سبب إلغاء الاستحقاق.")
            elif charge.payments.filter(is_voided=False).exists():
                messages.error(request, "لا يمكن إلغاء استحقاق عليه إيصالات سداد فعالة؛ راجع الإيصالات أولًا.")
            elif not charge.is_cancelled:
                charge.is_cancelled = True
                charge.cancellation_reason = reason
                charge.cancelled_by = request.user
                charge.cancelled_at = timezone.now()
                charge.save(update_fields=["is_cancelled", "cancellation_reason", "cancelled_by", "cancelled_at"])
                messages.success(request, "تم إلغاء الاستحقاق مع الاحتفاظ بسجله.")
    return redirect("students:finance_charges")


@login_required
@permission_required("students.view_paymentreceipt", raise_exception=True)
@permission_required("students.print_reports", raise_exception=True)
def receipt_print(request, pk):
    receipt = get_object_or_404(PaymentReceipt.objects.select_related("charge__student", "charge__term", "received_by"), pk=pk)
    return render(request, "students/receipt_print.html", {"receipt": receipt})
