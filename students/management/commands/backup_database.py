import os
import shutil
import sqlite3
import subprocess
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Create a secure database backup and prune expired backup files."

    def handle(self, *args, **options):
        backup_dir = Path(getattr(settings, "BACKUP_DIR", settings.BASE_DIR / "backups"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        engine = connection.settings_dict["ENGINE"]

        try:
            if engine.endswith("postgresql"):
                filename = f"student_affairs_{stamp}.dump"
                target = backup_dir / filename
                env = os.environ.copy()
                env["PGPASSWORD"] = connection.settings_dict.get("PASSWORD", "")
                db = connection.settings_dict
                command = [
                    "pg_dump", "--format=custom", "--no-owner", "--no-privileges",
                    "--host", str(db.get("HOST") or "localhost"),
                    "--port", str(db.get("PORT") or "5432"),
                    "--username", str(db.get("USER") or ""),
                    "--dbname", str(db["NAME"]),
                    "--file", str(target),
                ]
                subprocess.run(command, env=env, check=True, capture_output=True, text=True)
            elif engine.endswith("sqlite3"):
                source = connection.settings_dict["NAME"]
                if str(source) == ":memory:":
                    raise CommandError("لا يمكن إنشاء نسخة احتياطية دائمة من قاعدة بيانات SQLite الموجودة في الذاكرة.")
                filename = f"student_affairs_{stamp}.sqlite3"
                target = backup_dir / filename
                connection.ensure_connection()
                destination = sqlite3.connect(str(target))
                try:
                    connection.connection.backup(destination)
                finally:
                    destination.close()
            else:
                raise CommandError(f"محرك قاعدة البيانات غير مدعوم للنسخ الاحتياطي: {engine}")
            os.chmod(target, 0o600)
            if not target.exists() or target.stat().st_size == 0:
                target.unlink(missing_ok=True)
                raise CommandError("ملف النسخة الاحتياطية فارغ؛ لم يتم اعتماد النسخة.")
            if engine.endswith("postgresql"):
                subprocess.run(
                    ["pg_restore", "--list", str(target)],
                    check=True, capture_output=True, text=True,
                )
            else:
                check_db = sqlite3.connect(str(target))
                try:
                    integrity = check_db.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    check_db.close()
                if integrity != "ok":
                    target.unlink(missing_ok=True)
                    raise CommandError(f"فشل فحص سلامة نسخة SQLite: {integrity}")

            retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
            cutoff = timezone.now() - timedelta(days=max(1, retention_days))
            removed = 0
            for old in backup_dir.iterdir():
                if old.is_file() and old != target and old.name.startswith("student_affairs_"):
                    if timezone.datetime.fromtimestamp(old.stat().st_mtime, tz=timezone.get_current_timezone()) < cutoff:
                        old.unlink()
                        removed += 1
            self.stdout.write(self.style.SUCCESS(
                f"تم إنشاء النسخة الاحتياطية: {target.name} ({target.stat().st_size} bytes). "
                f"النسخ المحذوفة لانتهاء مدة الاحتفاظ: {removed}"
            ))
        except FileNotFoundError as exc:
            raise CommandError("أداة pg_dump غير موجودة. تأكد من تثبيت postgresql-client داخل صورة الخادم.") from exc
        except subprocess.CalledProcessError as exc:
            target.unlink(missing_ok=True)
            raise CommandError(f"فشل pg_dump: {exc.stderr or exc}") from exc
