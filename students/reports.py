from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Q
from django.http import HttpResponse
from django.shortcuts import render
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from .models import Student, StudentEnrollment, CourseRegistration, StudentCharge, PaymentReceipt

def _filtered(request):
    kind = request.GET.get("type", "students")
    year = request.GET.get("year", "").strip()
    semester = request.GET.get("semester", "").strip()
    department = request.GET.get("department", "").strip()
    level = request.GET.get("level", "").strip()
    status = request.GET.get("status", "").strip()
    students = Student.objects.filter(is_archived=False)
    if department: students = students.filter(department=department)
    if level: students = students.filter(academic_year=level)
    if status: students = students.filter(study_status=status)
    enrollments = StudentEnrollment.objects.select_related("student", "term")
    if year: enrollments = enrollments.filter(term__academic_year=year)
    if semester: enrollments = enrollments.filter(term__semester=semester)
    if department: enrollments = enrollments.filter(department=department)
    if level: enrollments = enrollments.filter(level=level)
    if status: enrollments = enrollments.filter(status=status)
    return kind, students, enrollments

@login_required
def reports_home(request):
    kind, students, enrollments = _filtered(request)
    rows, headers, title = [], [], "تقرير بيانات الطلاب"
    if kind == "grades":
        regs = CourseRegistration.objects.select_related("enrollment__student", "enrollment__term", "course")
        if request.GET.get("year"): regs = regs.filter(enrollment__term__academic_year=request.GET["year"])
        if request.GET.get("semester"): regs = regs.filter(enrollment__term__semester=request.GET["semester"])
        if request.GET.get("department"): regs = regs.filter(enrollment__department=request.GET["department"])
        if request.GET.get("level"): regs = regs.filter(enrollment__level=request.GET["level"])
        if request.GET.get("status"): regs = regs.filter(result_status=request.GET["status"])
        headers = ["الرقم الجامعي","اسم الطالب","العام الجامعي","الفصل","القسم","الفرقة","كود المادة","اسم المادة","أعمال السنة","الامتحان","المجموع","التقدير","النتيجة"]
        rows = [[r.enrollment.student.university_id,r.enrollment.student.full_name,r.enrollment.term.academic_year,r.enrollment.term.get_semester_display(),r.enrollment.department,r.enrollment.level,r.course.code,r.course.name,r.coursework_score,r.exam_score,r.total_score,r.grade,r.get_result_status_display()] for r in regs]
        title = "تقرير الدرجات والنتائج"
    elif kind == "finance":
        charges = StudentCharge.objects.select_related("student","term").prefetch_related("payments").filter(is_cancelled=False)
        if request.GET.get("year"): charges = charges.filter(term__academic_year=request.GET["year"])
        if request.GET.get("semester"): charges = charges.filter(term__semester=request.GET["semester"])
        if request.GET.get("department"): charges = charges.filter(student__department=request.GET["department"])
        if request.GET.get("level"): charges = charges.filter(student__academic_year=request.GET["level"])
        headers = ["الرقم الجامعي","اسم الطالب","العام الجامعي","بيان الاستحقاق","المستحق","المحصل","المتبقي","الحالة"]
        for c in charges:
            paid = c.payments.filter(is_voided=False).aggregate(v=Sum("amount"))["v"] or Decimal("0")
            rows.append([c.student.university_id,c.student.full_name,c.term.academic_year if c.term else "",c.title,c.amount,paid,c.amount-paid,"مسدد" if c.amount<=paid else ("جزئي" if paid else "غير مسدد")])
        title = "تقرير الرسوم والمتأخرات"
    else:
        headers = ["الرقم الجامعي","اسم الطالب","الفرقة","القسم","الشعبة","الحالة الدراسية","الهاتف"]
        rows = [[s.university_id,s.full_name,s.academic_year,s.department,s.division,s.get_study_status_display(),s.phone] for s in students]
    departments = Student.objects.exclude(department="").values_list("department",flat=True).distinct().order_by("department")
    levels = Student.objects.exclude(academic_year="").values_list("academic_year",flat=True).distinct().order_by("academic_year")
    years = StudentEnrollment.objects.values_list("term__academic_year",flat=True).distinct().order_by("-term__academic_year")
    if request.GET.get("export") == "xlsx":
        wb=Workbook(); ws=wb.active; ws.title="التقرير"
        ws.append([title]); ws.append(headers)
        for row in rows: ws.append([str(v) if v is not None else "" for v in row])
        ws.freeze_panes="A3"; ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:
            cell.font=Font(bold=True,color="FFFFFF",size=14); cell.fill=PatternFill("solid",fgColor="174A7E"); cell.alignment=Alignment(horizontal="center")
        for cell in ws[2]:
            cell.font=Font(bold=True,color="FFFFFF"); cell.fill=PatternFill("solid",fgColor="386A91"); cell.alignment=Alignment(horizontal="center")
        for column in ws.columns:
            letter=column[0].column_letter
            ws.column_dimensions[letter].width=min(max(max(len(str(c.value or "")) for c in column)+3,14),36)
            for cell in column: cell.alignment=Alignment(horizontal="right",vertical="center")
        response=HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"]='attachment; filename="student_report.xlsx"'
        wb.save(response); return response
    return render(request,"students/reports.html",{"title":title,"headers":headers,"rows":rows,"departments":departments,"levels":levels,"years":years,"kind":kind,"count":len(rows),"filters":request.GET})

