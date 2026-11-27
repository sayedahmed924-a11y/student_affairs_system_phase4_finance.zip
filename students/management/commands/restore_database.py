import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections


def _prepare_media_restore(archive_path):
    media_root = Path(settings.MEDIA_ROOT).resolve()
    media_root.parent.mkdir(parents=True, exist_ok=True)
    staging_parent = Path(tempfile.mkdtemp(prefix=".student-affairs-media-", dir=str(media_root.parent)))
    staging = staging_parent / "new"
    staging.mkdir()
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                relative = PurePosixPath(member.name)
                if (
                    relative.is_absolute()
                    or not relative.parts
                    or ".." in relative.parts
                    or "\\" in member.name
                    or member.issym()
                    or member.islnk()
                    or not (member.isfile() or member.isdir())
                ):
                    raise CommandError(f"مسار أو نوع ملف غير آمن داخل أرشيف media: {member.name}")
                destination = staging.joinpath(*relative.parts).resolve()
                if destination != staging and staging not in destination.parents:
                    raise CommandError("أرشيف media يحاول الكتابة خارج مجلد الملفات.")
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise CommandError(f"تعذر قراءة الملف: {member.name}")
                    with stream, destination.open("wb") as output:
                        shutil.copyfileobj(stream, output)
                    os.chmod(destination, 0o600)
        return media_root, staging_parent, staging
    except Exception:
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise


def _install_media_restore(media_root, staging_parent, staging):
    previous = staging_parent / "previous"
    moved_previous = False
    try:
        if media_root.exists():
            os.replace(media_root, previous)
            moved_previous = True
        os.replace(staging, media_root)
    except Exception:
        if moved_previous and previous.exists() and not media_root.exists():
            os.replace(previous, media_root)
        raise
    finally:
        if previous.exists():
            shutil.rmtree(previous, ignore_errors=True)
        shutil.rmtree(staging_parent, ignore_errors=True)


class Command(BaseCommand):
    help = "Restore database and matching media archive. Run while web and backup services are stopped."

    def add_arguments(self, parser):
        parser.add_argument("filename", help="Database backup filename inside BACKUP_DIR.")
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
            raise CommandError("ملف قاعدة البيانات الاحتياطي غير موجود أو غير صالح.")

        engine = connection.settings_dict["ENGINE"]
        if engine.endswith("postgresql") and not filename.endswith(".dump"):
            raise CommandError("امتداد النسخة لا يتوافق مع PostgreSQL.")
        if engine.endswith("sqlite3") and not filename.endswith(".sqlite3"):
            raise CommandError("امتداد النسخة لا يتوافق مع SQLite.")
        if not (engine.endswith("postgresql") or engine.endswith("sqlite3")):
            raise CommandError(f"محرك قاعدة البيانات غير مدعوم: {engine}")

        media_name = Path(filename).stem + "_media.tar.gz"
        media_archive = (backup_dir / media_name).resolve()
        if media_archive.parent != backup_dir or not media_archive.is_file() or media_archive.stat().st_size == 0:
            raise CommandError("ملف media المرتبط بهذه النسخة غير موجود؛ لا يمكن ضمان استعادة المستندات.")

        # Create a safety snapshot of both the current database and media before restore.
        call_command("backup_database")
        media_root, staging_parent, staging = _prepare_media_restore(media_archive)

        try:
            if engine.endswith("postgresql"):
                env = os.environ.copy()
                env["PGPASSWORD"] = connection.settings_dict.get("PASSWORD", "")
                db = connection.settings_dict
                subprocess.run([
                    "pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges",
                    "--exit-on-error", "--single-transaction",
                    "--host", str(db.get("HOST") or "localhost"),
                    "--port", str(db.get("PORT") or "5432"),
                    "--username", str(db.get("USER") or ""),
                    "--dbname", str(db["NAME"]), str(source),
                ], env=env, check=True, capture_output=True, text=True)
            else:
                destination = Path(connection.settings_dict["NAME"]).resolve()
                if source == destination:
                    raise CommandError("ملف النسخة لا يمكن أن يكون هو ملف قاعدة البيانات الحالية.")
                connections.close_all()
                replacement = destination.with_suffix(destination.suffix + ".restore")
                shutil.copy2(source, replacement)
                os.replace(replacement, destination)
                os.chmod(destination, 0o600)

            _install_media_restore(media_root, staging_parent, staging)
        except FileNotFoundError as exc:
            shutil.rmtree(staging_parent, ignore_errors=True)
            raise CommandError("أداة pg_restore غير موجودة داخل صورة الخادم.") from exc
        except subprocess.CalledProcessError as exc:
            shutil.rmtree(staging_parent, ignore_errors=True)
            raise CommandError(f"فشلت استعادة قاعدة البيانات: {exc.stderr or exc}") from exc
        except Exception:
            shutil.rmtree(staging_parent, ignore_errors=True)
            raise

        self.stdout.write(self.style.SUCCESS(
            f"تمت استعادة قاعدة البيانات والملفات من {filename} بنجاح. أعد تشغيل خدمات التطبيق."
        ))
