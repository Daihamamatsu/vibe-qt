import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 開発用の不安全なフォールバックキー。本番環境では必ず環境変数で上書きすること
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-replace-me')

# 安全側で既定 False。開発環境では docker-compose.yml が true を明示
DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true', '1', 'yes')

# DEBUG のときのみ '*' を許可（開発用の便宜）。本番は明示的なホストのみ
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = os.environ.get(
        'DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1'
    ).split(',')

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'stockapp.app',
]

MIDDLEWARE = [
    'django.middleware.common.CommonMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

CORS_ALLOW_ALL_ORIGINS = True
ROOT_URLCONF = 'stockapp.urls'

TEMPLATES = []

WSGI_APPLICATION = 'stockapp.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db', 'stock.db'),
    }
}

STATIC_URL = '/static/'

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'