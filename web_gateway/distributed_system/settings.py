"""
Django settings for distributed_system project.
"""
import os
from pathlib import Path
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-f#ily09^b++&@r=4ovpvrsi%xa3w&pn@9-io$fh2@ns@+9tn_3'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# FIX 1: Allow all hosts so Render works
ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'base'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'distributed_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['templates'], # Ensure this folder exists!
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'distributed_system.wsgi.application'


# FIX 2: Hybrid Database Logic (Secure)
# ---------------------------------------------------------
# Check if running on Vercel (read-only environment)
IS_VERCEL = 'VERCEL' in os.environ

if IS_VERCEL:
    import shutil
    tmp_db = Path('/tmp/db.sqlite3')
    
    # Locate existing sqlite file to initialize /tmp
    possible_sources = [
        BASE_DIR / 'db.sqlite3',
        BASE_DIR / 'web_gateway' / 'db.sqlite3',
        Path(__file__).resolve().parent.parent / 'db.sqlite3',
        Path(__file__).resolve().parent.parent.parent / 'db.sqlite3',
    ]
    
    if not tmp_db.exists():
        for src in possible_sources:
            if src.exists():
                try:
                    shutil.copy2(src, tmp_db)
                    break
                except Exception:
                    pass
    db_name = tmp_db
else:
    db_name = BASE_DIR / 'db.sqlite3'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': db_name,
    }
}

# If DATABASE_URL exists (e.g. Postgres on Render or Neon/Supabase), use it automatically
database_url = os.environ.get("DATABASE_URL")
if database_url:
    DATABASES["default"] = dj_database_url.parse(database_url)
# ---------------------------------------------------------


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# FIX 3: Add this for Render to know where to collect static files
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
# STATICFILES_DIRS =[BASE_DIR / 'static']  <-- Uncomment this if you have a custom static folder

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication URLs
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashbord'
LOGOUT_REDIRECT_URL = 'home'

# Serverless Session Handling (Signed Cookies)
# Keeps the user logged in across multiple Vercel Lambda instances
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 1209600  # 2 weeks
