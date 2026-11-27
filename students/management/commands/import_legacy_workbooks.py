import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from students.models import FeeCatalog, Student


def norm(value):
    text = str(value or "").strip().lower()
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[\s_\-./:()]+", "", text)
    return text


ALIASES = {
    "student_id": {"كودالطالب", "الرقمالجامعي", "كود", "universityid", "studentid", "studentcode"},
    "financial_code": {"الكودالمالي", "كودمالي", "financecode", "financialcode"},
    "name": {"الاسم", "اسمالطالب", "اسم", "fullname", "studentname"},
    "nationality": {"الجنسية", "nationality"},
    "level": {"المستويالدراسي", "المستوي", "الفرقة", "الفرقه", "academicyear", "level", "year"},
    "department": {"القسم", "الشعبة", "department"},
    "program": {"البرنامج", "program"},
    "service": {"نوعالخدمة", "الخدمة", "بيانالخدمة", "service", "servicetype"},
    "amount": {"المبلغبالارقام", "سعرالخدمةبالدولار", "المبلغ", "القيمة", "amount", "price"},
    "amount_words": {"المبلغبالحروف", "المبلغكتابة", "amountwords"},
    "bank": {"اسمالبنك", "البنك", "bank", "bankname"},
}


def header_key(value):
    key = norm(value)
    for field, aliases in ALIASES.items():
        normalized_aliases = {norm(x) for x in aliases}
        if key in normalized_aliases or any(key.startswith(alias) and len(key) - len(alias) <= 4 for alias in normalized_aliases):
            return field
    return None


def decimal_value(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    cleaned = str(value).replace(",", "").replace("$", "").replace("جنيه", "").replace("دولار", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return Decimal(match.group())
    except InvalidOperation:
        return None


def infer_category(filename, sheet):
    text = norm(filename + " " + sheet)
    if "نادي" in text or "club" in text:
        return "expat_club", "EGP"
    if "دولاري" in text or "دولار" in text or "dollar" in text:
        return "dollar_services", "USD"
    if "وزاره" in text or "ministry" in text:
        return "ministry", "USD"
    return "other", "EGP"


class Command(BaseCommand):
    help = "Import Arabic/English legacy student and finance Excel workbooks without deleting existing records."

    def add_arguments(self, parser):
        parser.add_argument("files", nargs="+", help="XLSX file paths")
        parser.add_argument("--dry-run", action="store_true", help="Validate and report only; do not save")
        parser.add_argument("--category", choices=["ministry", "expat_club", "dollar_services", "other"])
        parser.add_argument("--currency", choices=["USD", "EGP"])

    def handle(self, *args, **options):
        user = getattr(self, "import_user", None)
        if user is None:
            from django.contrib.auth import get_user_model
            user = get_user_model().objects.filter(is_superuser=True).first()
        if not user and not options["dry_run"]:
            raise CommandError("أنشئ مستخدم مدير أولاً أو نفّذ الاستيراد في وضع --dry-run.")
        totals = {"students_created": 0, "students_updated": 0, "fees_created": 0, "fees_existing": 0, "skipped": 0}
        for filename in options["files"]:
            path = Path(filename)
            if not path.exists() or path.suffix.lower() != ".xlsx":
                raise CommandError(f"ملف غير موجود أو ليس XLSX: {filename}")
            workbook = load_workbook(path, read_only=True, data_only=True)
            for sheet in workbook.worksheets:
                rows = sheet.iter_rows(values_only=True)
                buffered = []
                header = None
                for index, row in enumerate(rows):
                    buffered.append(row)
                    if index >= 20:
                        break
                    mapping = {}
                    for col, value in enumerate(row):
                        field = header_key(value)
                        if field and field not in mapping:
                            mapping[field] = col
                    if len(mapping) >= 2 and ("student_id" in mapping or "service" in mapping):
                        header = (index, mapping)
                        break
                if not header:
                    continue
                header_row, mapping = header
                category, currency = infer_category(path.name, sheet.title)
                category = options["category"] or category
                currency = options["currency"] or ("EGP" if category == "expat_club" else "USD" if category in ("ministry", "dollar_services") else currency)
                for row_number, row in enumerate(rows, start=header_row + 2):
                    if not row or not any(value not in (None, "") for value in row):
                        continue
                    data = {field: (row[col] if col < len(row) else None) for field, col in mapping.items()}
                    if "student_id" in mapping and data.get("student_id") not in (None, "") and data.get("name"):
                        uid = str(data["student_id"]).strip()
                        defaults = {
                            "full_name": str(data["name"]).strip(),
                            "nationality": str(data.get("nationality") or "").strip(),
                            "academic_year": str(data.get("level") or "").strip(),
                            "department": str(data.get("department") or "").strip(),
                            "financial_code": str(data.get("financial_code") or "").strip(),
                            "program": str(data.get("program") or "").strip(),
                        }
                        defaults = {k: v for k, v in defaults.items() if v}
                        if options["dry_run"]:
                            totals["students_updated" if Student.objects.filter(university_id=uid).exists() else "students_created"] += 1
                        else:
                            with transaction.atomic():
                                obj, created = Student.objects.update_or_create(university_id=uid, defaults=defaults)
                            totals["students_created" if created else "students_updated"] += 1
                    if "service" in mapping and data.get("service"):
                        amount = decimal_value(data.get("amount"))
                        if amount is None or amount <= 0:
                            totals["skipped"] += 1
                            continue
                        fee_defaults = {
                            "amount_words": str(data.get("amount_words") or "").strip(),
                            "bank_name": str(data.get("bank") or "").strip(),
                            "source_workbook": path.name,
                            "source_sheet": sheet.title,
                        }
                        exists = FeeCatalog.objects.filter(category=category, name=str(data["service"]).strip(),
                            amount=amount, currency=currency).exists()
                        if options["dry_run"]:
                            totals["fees_existing" if exists else "fees_created"] += 1
                        else:
                            _, created = FeeCatalog.objects.update_or_create(
                                category=category, name=str(data["service"]).strip(), amount=amount, currency=currency,
                                defaults=fee_defaults)
                            totals["fees_created" if created else "fees_existing"] += 1
            workbook.close()
        self.stdout.write(self.style.SUCCESS(
            ("معاينة فقط - " if options["dry_run"] else "انتهى الاستيراد - ") +
            " | ".join(f"{key}: {value}" for key, value in totals.items())
        ))
