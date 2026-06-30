import os
import dj_database_url
from decouple import config
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================
# SECURITY & DEBUG
# ============================================================
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)

# ✅ Render.com allowed hosts
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.onrender.com',
    'rentsure-kenya.onrender.com',  # Replace with your actual Render URL
]

# ============================================================
# INSTALLED APPS
# ============================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',           # PostGIS
    'rest_framework',
    'leaflet',
    'phonenumber_field',
    'users',
    'properties',
    'payments',
    'security',
    'channels',
    'tailwind',
    'theme',
    'corsheaders',
]

# ============================================================
# TAILWIND
# ============================================================
TAILWIND_APP_NAME = 'theme'

# ============================================================
# MIDDLEWARE
# ============================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # ✅ For static files
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ============================================================
# URL CONFIG
# ============================================================
ROOT_URLCONF = 'rentsure.urls'

# ============================================================
# TEMPLATES
# ============================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'users.context_processors.unread_notifications',
            ],
        },
    },
]

# ============================================================
# DATABASE (PostGIS) – Render.com ready
# ============================================================
if 'DATABASE_URL' in os.environ:
    # Production: Use Render.com's PostgreSQL
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Development: Use local PostgreSQL
    DATABASES = {
        'default': {
            'ENGINE': 'django.contrib.gis.db.backends.postgis',
            'NAME': config('DB_NAME', default='rentsure_kenya'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }

# ============================================================
# GDAL / PROJ (Render.com compatible)
# ============================================================
if 'RENDER' in os.environ:
    # Render.com paths
    GDAL_LIBRARY_PATH = os.environ.get('GDAL_LIBRARY_PATH', '/usr/lib/libgdal.so')
    os.environ['GDAL_DATA'] = os.environ.get('GDAL_DATA', '/usr/share/gdal')
    os.environ['PROJ_LIB'] = os.environ.get('PROJ_LIB', '/usr/share/proj')
else:
    # Windows development
    GDAL_LIBRARY_PATH = r'C:\OSGeo4W\bin\gdal313.dll'
    os.environ['GDAL_DATA'] = r'C:\OSGeo4W\apps\gdal\share\gdal'
    os.environ['PROJ_LIB'] = r'C:\OSGeo4W\share\proj'

# ============================================================
# USER MODEL
# ============================================================
AUTH_USER_MODEL = 'users.User'

# ============================================================
# STATIC & MEDIA FILES (Render.com compatible)
# ============================================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ✅ WhiteNoise for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ============================================================
# AUTHENTICATION
# ============================================================
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'

AUTHENTICATION_BACKENDS = [
    'users.backends.BlacklistAwareBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# ============================================================
# LEAFLET (maps)
# ============================================================
LEAFLET_CONFIG = {
    'DEFAULT_CENTER': (-1.286389, 36.817223),
    'DEFAULT_ZOOM': 12,
    'MIN_ZOOM': 6,
    'MAX_ZOOM': 18,
}

# ============================================================
# CHANNELS (WebSockets)
# ============================================================
ASGI_APPLICATION = 'rentsure.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# ============================================================
# EMAIL
# ============================================================
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@rentsurekenya.co.ke'

# ============================================================
# TIMEZONE
# ============================================================
TIME_ZONE = 'Africa/Nairobi'
USE_TZ = True

# ============================================================
# CACHING
# ============================================================
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'my_cache_table',
    }
}

# ============================================================
# SECURITY (Production)
# ============================================================
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ============================================================
# THIRD-PARTY APP SETTINGS
# ============================================================
PHONENUMBER_DEFAULT_REGION = 'KE'

# CORS (if needed)
CORS_ALLOW_ALL_ORIGINS = DEBUG  # Only for development