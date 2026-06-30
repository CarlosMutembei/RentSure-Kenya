import os
from decouple import config
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================
# SECURITY & DEBUG
# ============================================================
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = ['*']   # Update in production

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
    # 'django_cron',
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
        'DIRS': [BASE_DIR / 'templates'],          # Custom admin templates go here
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
# DATABASE (PostGIS)
# ============================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
    }
}

# ============================================================
# GDAL / PROJ (Windows)
# ============================================================
# Set GDAL library path (adjust version if needed)
GDAL_LIBRARY_PATH = r'C:\OSGeo4W\bin\gdal313.dll'

# Set environment variables for GDAL and PROJ
os.environ['GDAL_DATA'] = r'C:\OSGeo4W\apps\gdal\share\gdal'
os.environ['PROJ_LIB'] = r'C:\OSGeo4W\share\proj'   # if this folder exists, else comment out

# ============================================================
# USER MODEL
# ============================================================
AUTH_USER_MODEL = 'users.User'

# ============================================================
# STATIC & MEDIA FILES
# ============================================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']          # For custom CSS, JS, images
STATIC_ROOT = BASE_DIR / 'staticfiles'            # For collectstatic (production)

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

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
    'DEFAULT_CENTER': (-1.286389, 36.817223),   # Nairobi
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
        'BACKEND': 'channels.layers.InMemoryChannelLayer',   # For development
    },
}

# ============================================================
# EMAIL (development)
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
# ADMIN CUSTOMIZATION (optional – can also be set in admin.py)
# ============================================================
# You can set these in admin.py instead, but here for completeness:
# from django.contrib.admin import site
# site.site_header = "RentSure Kenya Admin"
# site.site_title = "RentSure Kenya"
# site.index_title = "Welcome to RentSure Kenya Admin Panel"

# ============================================================
# LOGGING (optional – add if needed)
# ============================================================
# LOGGING = { ... }

# ============================================================
# THIRD-PARTY APP SETTINGS
# ============================================================
# django-phonenumber-field
PHONENUMBER_DEFAULT_REGION = 'KE'