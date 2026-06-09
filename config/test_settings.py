from .settings import *  # noqa: F401,F403

SECRET_KEY = "django-insecure-ngofund-test-secret-key-2026-keep-this-long"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

MEDIA_ROOT = BASE_DIR / "test-media"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
