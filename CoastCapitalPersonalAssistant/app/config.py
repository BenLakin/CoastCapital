import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Flask ─────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production")
    API_KEY = os.environ.get("API_KEY", "")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # ── MySQL ─────────────────────────────────────────────────────────────────
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "coastcapital-mysql")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
    MYSQL_USER = os.environ.get("MYSQL_USER", "dbadmin")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "assistant_silver")

    # ── iCloud Email ──────────────────────────────────────────────────────────
    ICLOUD_EMAIL = os.environ.get("ICLOUD_EMAIL", "")
    ICLOUD_APP_PASSWORD = os.environ.get("ICLOUD_APP_PASSWORD", "")
    ICLOUD_IMAP_HOST = "imap.mail.me.com"
    ICLOUD_IMAP_PORT = 993
    ICLOUD_SMTP_HOST = "smtp.mail.me.com"
    ICLOUD_SMTP_PORT = 587

    # ── iCloud Calendar (CalDAV) ──────────────────────────────────────────────
    CALDAV_URL = "https://caldav.icloud.com"

    # ── Anthropic Claude ──────────────────────────────────────────────────────
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")

    # ── News ──────────────────────────────────────────────────────────────────
    NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

    # ── Owner & Family Contacts ───────────────────────────────────────────────
    OWNER_NAME = os.environ.get("OWNER_NAME", "Owner")
    OWNER_CITY = os.environ.get("OWNER_CITY", "")
    WEATHER_ZIP = os.environ.get("WEATHER_ZIP", "94025")
    KIM_LAKIN_EMAIL = os.environ.get("KIM_LAKIN_EMAIL", "")
    FAMILY_EMAILS_RAW = os.environ.get("FAMILY_EMAILS", "")

    @classmethod
    def family_email_list(cls) -> list[str]:
        emails = []
        if cls.KIM_LAKIN_EMAIL:
            emails.append(cls.KIM_LAKIN_EMAIL)
        for e in cls.FAMILY_EMAILS_RAW.split(","):
            e = e.strip()
            if e and e not in emails:
                emails.append(e)
        return emails

    @classmethod
    def family_contacts(cls) -> dict:
        contacts = {}
        if cls.KIM_LAKIN_EMAIL:
            contacts["Kim Lakin"] = cls.KIM_LAKIN_EMAIL
        for e in cls.FAMILY_EMAILS_RAW.split(","):
            e = e.strip()
            if e:
                contacts[e.split("@")[0].title()] = e
        return contacts
