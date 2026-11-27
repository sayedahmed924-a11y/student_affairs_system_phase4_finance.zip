from decimal import Decimal
from django.test import SimpleTestCase

from students.management.commands.import_legacy_workbooks import (
    decimal_value, header_key, infer_category, norm,
)


class LegacyWorkbookParsingTests(SimpleTestCase):
    def test_arabic_student_headers(self):
        self.assertEqual(header_key("كود الطالب"), "student_id")
        self.assertEqual(header_key("المستوى الدراسى 2026"), "level")
        self.assertEqual(header_key("اسم الطالب"), "name")

    def test_arabic_fee_headers(self):
        self.assertEqual(header_key("نوع الخدمة"), "service")
        self.assertEqual(header_key("سعر الخدمة بالدولار"), "amount")
        self.assertEqual(header_key("المبلغ بالحروف"), "amount_words")

    def test_numeric_amount_parsing(self):
        self.assertEqual(decimal_value("1,250.50 $"), Decimal("1250.50"))
        self.assertEqual(decimal_value(300), Decimal("300"))
        self.assertIsNone(decimal_value("غير محدد"))

    def test_category_and_currency_are_separated(self):
        self.assertEqual(infer_category("امر توريد رسوم الوزارة.xlsx", "الرسوم"), ("ministry", "USD"))
        self.assertEqual(infer_category("امر توريد نادى الوافدي.xlsx", "الرسوم"), ("expat_club", "EGP"))
        self.assertEqual(infer_category("امر توريد الخدمات الدولارية.xlsx", "الخدمات"), ("dollar_services", "USD"))
