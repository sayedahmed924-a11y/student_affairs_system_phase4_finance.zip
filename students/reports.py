from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from .models import Student, StudentEnrollment, CourseRegistration, StudentCharge


def _filtered(request):
    kind = request.GET.get("type", "students")
    year = request.GET.get("year", "").strip()
    semester = request.GET.get("semester", "").strip()
    department = request.GET.get("department", "").strip()
    level = request.GET.get("level", "").strip()
    status = request.GET.get("status", "").strip()
    university_id = request.GET.get("university_id", "").strip()

    students = Student.objects.filter(is_archived=False)
    if department:
        students = students.filter(department=department)
    if level:
        students = students.filter(academic_year=level)
    if status and kind == "students":
        students = students.filter(study_status=status)
    if university_id:
        students = students.filter(university_id__icontains=university_id)

    enrollments = StudentEnrollment.objects.select_related("student", "term")
    if year:
        enrollments = enrollments.filter(term__academic_year=year)
    if semester:
        enrollments = enrollments.filter(term__semester=semester)
    if department:
        enrollments = enrollments.filter(department=department)
    if level:
        enrollments = enrollments.filter(level=level)
    if status and kind == "enrollments":
        enrollments = enrollments.filter(status=status)
    return kind, students, enrollments


def _filtered_registrations(request):
    regs = CourseRegistration.objects.select_related(
        "enrollment__student", "enrollment__term", "course"
    )
    params = request.GET
    if params.get("year"):
        regs = regs.filter(enrollment__term__academic_year=params["year"])
    if params.get("semester"):
        regs = regs.filter(enrollment__term__semester=params["semester"])
    if params.get("department"):
        regs = regs.filter(enrollment__department=params["department"])
    if params.get("level"):
        regs = regs.filter(enrollment__level=params["level"])
    if params.get("status"):
        regs = regs.filter(result_status=params["status"])
    if params.get("university_id"):
        regs = regs.filter(enrollment__student__university_id__icontains=params["university_id"].strip())
    return regs


@login_required
def reports_home(request):
    kind, students, enrollments = _filtered(request)
    rows, headers = [], []
    title = "تقرير بيانات الطلاب"
    stats = {}

    if kind == "grades":
        regs = _filtered_registrations(request)
        headers = ["الرقم الجامعي", "اسم الطالب", "العام الجامعي", "الفصل", "القسم",
                   "الفرقة", "كود المادة", "اسم المادة", "أعمال السنة", "الامتحان",
                   "المجموع", "التقدير", "النتيجة"]
        rows = [[r.enrollment.student.university_id, r.enrollment.student.full_name,
                 r.enrollment.term.academic_year, r.enrollment.term.get_semester_display(),
                 r.enrollment.department, r.enrollment.level, r.course.code, r.course.name,
                 r.coursework_score, r.exam_score, r.total_score, r.grade,
                 r.get_result_status_display()] for r in regs]
        title = "تقرير الدرجات وكشف النتائج"
        stats = {
            "total": regs.count(),
            "passed": regs.filter(result_status="passed").count(),
            "failed": regs.filter(result_status="failed").count(),
            "pending": regs.filter(result_status="pending").count(),
        }
    elif kind == "success":
        regs = _filtered_registrations(request)
        grouped = regs.values("course__code", "course__name").annotate(
            total=Count("id"),
            passed=Count("id", filter=Q(result_status="passed")),
            failed=Count("id", filter=Q(result_status="failed")),
            pending=Count("id", filter=Q(result_status="pending")),
        ).order_by("course__code")
        headers = ["كود المادة", "اسم المادة", "إجمالي الطلاب", "ناجح", "راسب",
                   "لم ترصد", "نسبة النجاح %"]
        for item in grouped:
            decided = item["passed"] + item["failed"]
            rate = (Decimal(item["passed"]) * Decimal("100") / Decimal(decided)) if decided else Decimal("0")
            rows.append([item["course__code"], item["course__name"], item["total"],
                         item["passed"], item["failed"], item["pending"], rate.quantize(Decimal("0.01"))])
        title = "تقرير النجاح والرسوب ونسب النجاح حسب المادة"
        stats = {
            "total": regs.count(),
            "passed": regs.filter(result_status="passed").count(),
            "failed": regs.filter(result_status="failed").count(),
            "pending": regs.filter(result_status="pending").count(),
        }
    elif kind == "finance":
        charges = StudentCharge.objects.select_related("student", "term").prefetch_related("payments").filter(is_cancelled=False)
        if request.GET.get("year"):
            charges = charges.filter(term__academic_year=request.GET["year"])
        if request.GET.get("semester"):
            charges = charges.filter(term__semester=request.GET["semester"])
        if request.GET.get("department"):
            charges = charges.filter(student__department=request.GET["department"])
        if request.GET.get("level"):
            charges = charges.filter(student__academic_year=request.GET["level"])
        if request.GET.get("university_id"):
            charges = charges.filter(student__university_id__icontains=request.GET["university_id"].strip())
        headers = ["الرقم الجامعي", "اسم الطالب", "العام الجامعي", "بيان الاستحقاق",
                   "المستحق", "المحصل", "المتبقي", "الحالة"]
        total_due = Decimal("0")
        total_paid = Decimal("0")
        for charge in charges:
            paid = charge.payments.filter(is_voided=False).aggregate(value=Sum("amount"))["value"] or Decimal("0")
            balance = charge.amount - paid
            total_due += charge.amount
            total_paid += paid
            rows.append([charge.student.university_id, charge.student.full_name,
                         charge.term.academic_year if charge.term else "", charge.title,
                         charge.amount, paid, balance,
                         "مسدد" if balance <= 0 else ("جزئي" if paid else "غير مسدد")])
        title = "تقرير الرسوم والتحصيل والمتأخرات"
        stats = {"due": total_due, "paid": total_paid, "balance": total_due - total_paid}
    elif kind == "enrollments":
        headers = ["الرقم الجامعي", "اسم الطالب", "العام الجامعي", "الفصل",
                   "الفرقة", "القسم", "حالة القيد", "تاريخ التسجيل"]
        rows = [[e.student.university_id, e.student.full_name, e.term.academic_year,
                 e.term.get_semester_display(), e.level, e.department,
                 e.get_status_display(), e.registered_at.strftime("%Y-%m-%d")]
                for e in enrollments]
        title = "كشف قيود الطلاب حسب الفصل الدراسي"
    else:
        if request.GET.get("year") or request.GET.get("semester"):
            students = students.filter(enrollments__in=enrollments).distinct()
        headers = ["الرقم الجامعي", "اسم الطالب", "الفرقة", "القسم", "الشعبة",
                   "الحالة الدراسية", "الهاتف"]
        rows = [[s.university_id, s.full_name, s.academic_year, s.department,
                 s.division, s.get_study_status_display(), s.phone] for s in students]
        title = "كشف بيانات الطلاب"

    departments = Student.objects.exclude(department="").values_list("department", flat=True).distinct().order_by("department")
    levels = Student.objects.exclude(academic_year="").values_list("academic_year", flat=True).distinct().order_by("academic_year")
    years = StudentEnrollment.objects.values_list("term__academic_year", flat=True).distinct().order_by("-term__academic_year")

    if request.GET.get("export") == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "التقرير"
        sheet.sheet_view.rightToLeft = True
        sheet.append([title])
        sheet.append(headers)
        for row in rows:
            sheet.append([str(value) if value is not None else "" for value in row])
        sheet.freeze_panes = "A3"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF", size=14)
            cell.fill = PatternFill("solid", fgColor="174A7E")
            cell.alignment = Alignment(horizontal="center")
        for cell in sheet[2]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="386A91")
            cell.alignment = Alignment(horizontal="center")
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(max(max(len(str(c.value or "")) for c in column) + 3, 14), 40)
            for cell in column:
                cell.alignment = Alignment(horizontal="right", vertical="center")
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="student_report.xlsx"'
        workbook.save(response)
        return response

    return render(request, "students/reports.html", {
        "title": title, "headers": headers, "rows": rows, "departments": departments,
        "levels": levels, "years": years, "kind": kind, "count": len(rows),
        "filters": request.GET, "stats": stats,
    })


@login_required
def student_full_report(request, pk):
    from .models import StudentAcademicEvent
    student = Student.objects.get(pk=pk)
    enrollments = StudentEnrollment.objects.filter(student=student).select_related("term").prefetch_related("course_registrations__course")
    events = StudentAcademicEvent.objects.filter(student=student).select_related("term", "recorded_by")
    charges = StudentCharge.objects.filter(student=student, is_cancelled=False).prefetch_related("payments")
    due = sum((c.amount for c in charges), Decimal("0"))
    paid = sum((c.paid_amount for c in charges), Decimal("0"))
    registrations = CourseRegistration.objects.filter(enrollment__student=student)
    context = {
        "student": student,
        "enrollments": enrollments,
        "events": events,
        "charges": charges,
        "total_due": due,
        "total_paid": paid,
        "balance": due - paid,
        "registrations_count": registrations.count(),
        "passed_count": registrations.filter(result_status="passed").count(),
        "failed_count": registrations.filter(result_status="failed").count(),
    }
    return render(request, "students/student_full_report.html", context)


@login_required
def student_financial_statement(request, pk):
    from .models import PaymentReceipt
    student = Student.objects.get(pk=pk)
    charges = StudentCharge.objects.filter(student=student, is_cancelled=False)
    receipts = PaymentReceipt.objects.filter(charge__student=student, is_voided=False).select_related("charge")
    entries = []
    for charge in charges:
        entries.append({
            "date": charge.created_at,
            "kind": "استحقاق",
            "description": charge.title,
            "reference": "",
            "debit": charge.amount,
            "credit": Decimal("0"),
        })
    for receipt in receipts:
        entries.append({
            "date": receipt.received_at,
            "kind": "سداد",
            "description": receipt.charge.title,
            "reference": receipt.receipt_number,
            "debit": Decimal("0"),
            "credit": receipt.amount,
        })
    entries.sort(key=lambda item: (item["date"], item["kind"] == "سداد"))
    running_balance = Decimal("0")
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for entry in entries:
        total_debit += entry["debit"]
        total_credit += entry["credit"]
        running_balance += entry["debit"] - entry["credit"]
        entry["balance"] = running_balance
    return render(request, "students/student_financial_statement.html", {
        "student": student, "entries": entries, "total_debit": total_debit,
        "total_credit": total_credit, "balance": running_balance,
    })
