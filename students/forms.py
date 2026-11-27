from django import forms
from .models import Student

class StudentForm(forms.ModelForm):
    # Snapshot of the record version loaded by the employee; used to reject stale forms.
    version_token = forms.CharField(required=False, widget=forms.HiddenInput())
    reason = forms.CharField(label="سبب الإضافة أو التعديل", widget=forms.Textarea(attrs={"rows": 2}))
    source_document = forms.FileField(label="مستند مؤيد (اختياري)", required=False)
    class Meta:
        model = Student
        fields = ["university_id", "full_name", "national_id", "nationality", "phone",
                  "address", "academic_year", "department", "division", "study_status", "notes"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2}), "notes": forms.Textarea(attrs={"rows": 2})}

class ImportForm(forms.Form):
    file = forms.FileField(label="ملف Excel")
    reason = forms.CharField(label="سبب التحديث", widget=forms.Textarea(attrs={"rows": 2}))

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError("حجم ملف Excel يتجاوز الحد المسموح (10 ميجابايت).")
        return uploaded


from .models import AcademicTerm, Course, StudentEnrollment, CourseRegistration, StudentAcademicEvent

class AcademicTermForm(forms.ModelForm):
    class Meta:
        model = AcademicTerm
        fields = ["name", "academic_year", "semester", "starts_on", "ends_on", "is_active"]
        widgets = {"starts_on": forms.DateInput(attrs={"type": "date"}),
                   "ends_on": forms.DateInput(attrs={"type": "date"})}

class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["code", "name", "department", "level", "credit_hours", "max_score", "pass_score", "excellent_percent", "very_good_percent", "good_percent", "is_active"]

    def clean(self):
        cleaned = super().clean()
        maximum = cleaned.get("max_score")
        passing = cleaned.get("pass_score")
        if maximum is not None and maximum <= 0:
            self.add_error("max_score", "النهاية العظمى يجب أن تكون أكبر من صفر.")
        if maximum is not None and passing is not None and not (0 <= passing <= maximum):
            self.add_error("pass_score", "درجة النجاح يجب أن تكون بين صفر والنهاية العظمى.")
        bands = [cleaned.get("excellent_percent"), cleaned.get("very_good_percent"), cleaned.get("good_percent"),
                 (passing / maximum * 100) if maximum and passing is not None else None]
        if all(value is not None for value in bands):
            if not (100 >= bands[0] > bands[1] > bands[2] > bands[3] >= 0):
                raise forms.ValidationError("حدود التقديرات يجب أن تكون تنازلية: امتياز ثم جيد جدًا ثم جيد ثم النجاح.")
        return cleaned

class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = StudentEnrollment
        fields = ["student", "term", "level", "department", "status", "notes"]

    def clean(self):
        cleaned = super().clean()
        student, term = cleaned.get("student"), cleaned.get("term")
        if student and term:
            duplicate = StudentEnrollment.objects.filter(student=student, term=term)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error("term", "هذا الطالب لديه قيد مسجل بالفعل في الفصل المختار.")
        return cleaned

class CourseRegistrationForm(forms.ModelForm):
    class Meta:
        model = CourseRegistration
        fields = ["enrollment", "course", "coursework_score", "exam_score",
                  "grade", "result_source", "result_reason"]

    def clean(self):
        cleaned = super().clean()
        for field in ("coursework_score", "exam_score"):
            value = cleaned.get(field)
            if value is not None and value < 0:
                self.add_error(field, "لا يمكن إدخال درجة سالبة.")
        return cleaned

class ReEnrollmentForm(forms.Form):
    student = forms.ModelChoiceField(queryset=Student.objects.filter(is_archived=False), label="الطالب")
    term = forms.ModelChoiceField(queryset=AcademicTerm.objects.all(), label="الفصل الدراسي")
    level = forms.CharField(label="الفرقة الدراسية")
    department = forms.CharField(label="القسم", required=False)
    reason = forms.CharField(label="سبب إعادة القيد", widget=forms.Textarea(attrs={"rows": 3}))
    reference_number = forms.CharField(label="رقم القرار", required=False)

class AcademicEventForm(forms.ModelForm):
    class Meta:
        model = StudentAcademicEvent
        fields = ["student", "term", "event_type", "event_date", "details",
                  "reason", "reference_number", "document"]
        widgets = {"event_date": forms.DateInput(attrs={"type": "date"})}

from .models import StudentCharge, PaymentReceipt

class StudentChargeForm(forms.ModelForm):
    class Meta:
        model = StudentCharge
        fields = ["student", "term", "title", "amount", "due_date", "notes"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("قيمة الاستحقاق يجب أن تكون أكبر من صفر.")
        return amount

class PaymentReceiptForm(forms.ModelForm):
    class Meta:
        model = PaymentReceipt
        fields = ["charge", "receipt_number", "amount", "method", "reference", "notes"]

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("المبلغ المدفوع يجب أن يكون أكبر من صفر.")
        return amount

class VoidReceiptForm(forms.Form):
    reason = forms.CharField(label="سبب إلغاء الإيصال", widget=forms.Textarea(attrs={"rows": 3}))
