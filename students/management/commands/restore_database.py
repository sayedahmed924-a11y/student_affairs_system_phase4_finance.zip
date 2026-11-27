import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections


class Command(BaseCommand):
    help = "Restore the database from a backup file. Run only while the web service is stopped."

    def add_arguments(self, parser):
        parser.add_argument("filename", help="Backup filename located inside BACKUP_DIR.")
        parser.add_argument("--confirm", required=True, help="Must be RESTORE to confirm destructive restore.")

    def handle(self, *args, **options):
        if options["confirm"] != "RESTORE":
            raise CommandError("تأكيد الاستعادة غير صحيح. استخدم --confirm RESTORE.")
        filename = options["filename"]
        if Path(filename).name != filename or filename in {".", ".."}:
            raise CommandError("اسم ملف النسخة غير صالح.")
        backup_dir = Path(getattr(settings, "BACKUP_DIR", settings.BASE_DIR / "backups")).resolve()
        source = (backup_dir / filename).resolve()
        if source.parent != backup_dir or not source.is_file() or source.stat().st_size == 0:
            raise CommandError("ملف النسخة غير موجود أو غير صالح داخل مجلد النسخ الاحتياطية.")

        engine = connection.settings_dict["ENGINE"]
        if engine.endswith("postgresql"):
            if not filename.endswith(".dump"):
                raise CommandError("امتداد النسخة لا يتوافق مع PostgreSQL.")
            env = os.environ.copy()
            env["PGPASSWORD"] = connection.settings_dict.get("PASSWORD", "")
            db = connection.settings_dict
            command = [
                "pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges",
                "--exit-on-error", "--single-transaction",
                "--host", str(db.get("HOST") or "localhost"),
                "--port", str(db.get("PORT") or "5432"),
                "--username", str(db.get("USER") or ""),
                "--dbname", str(db["NAME"]), str(source),
            ]
            try:
                subprocess.run(command, env=env, check=True, capture_output=True, text=True)
            except FileNotFoundError as exc:
                raise CommandError("أداة pg_restore غير موجودة داخل صورة الخادم.") from exc
            except subprocess.CalledProcessError as exc:
                raise CommandError(f"فشلت الاستعادة: {exc.stderr or exc}") from exc
        elif engine.endswith("sqlite3"):
            if not filename.endswith(".sqlite3"):
                raise CommandError("امتداد النسخة لا يتوافق مع SQLite.")
            destination = Path(connection.settings_dict["NAME"]).resolve()
            if source == destination:
                raise CommandError("ملف النسخة لا يمكن أن يكون هو ملف قاعدة البيانات الحالية.")
            connections.close_all()
            shutil.copy2(source, destination)
            os.chmod(destination, 0o600)
        else:
            raise CommandError(f"محرك قاعدة البيانات غير مدعوم للاستعادة: {engine}")

        self.stdout.write(self.style.SUCCESS(
            f"تمت استعادة قاعدة البيانات من {filename}. أعد تشغيل خدمة التطبيق وتحقق من البيانات."
        ))
