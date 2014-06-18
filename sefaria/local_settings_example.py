# An example of settings needed in a local_settings.py file which is ignored by git.
# copy this file to sefaria/local_settings.py and provide local info to run.

DEBUG = True
TEMPLATE_DEBUG = DEBUG
OFFLINE = False
DOWN_FOR_MAINTENANCE = False
MAINTENANCE_MESSAGE = ""


ADMINS = (
     ('Your Name', 'you@example.com'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3', # Add 'postgresql_psycopg2', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': '/path/to/your/sefaria/data/db.sqlite', # Or path to database file if using sqlite3.
        'USER': '',                      # Not used with sqlite3.
        'PASSWORD': '',                  # Not used with sqlite3.
        'HOST': '',                      # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': '/path/to/your/django_cache/',
    }
}

# To use a Redis Backend for Caching 
#CACHES = {
#    "default": {
#        "BACKEND": "redis_cache.cache.RedisCache",
#        "LOCATION": "127.0.0.1:6379:1",
#        "OPTIONS": {
#            "CLIENT_CLASS": "redis_cache.client.DefaultClient",
#            #"PASSWORD": "secretpassword", # Optional
#        },
#        "TIMEOUT": 60 * 60 * 24 * 30,
#    }
#}
#
#SESSION_ENGINE = "django.contrib.sessions.backends.cache"
#SESSION_CACHE_ALIAS = "default"

SECRET_KEY = 'insert your long random secret key here !'

STATICFILES_DIRS = (
    '/path/to/your/sefaria/static/',
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

TEMPLATE_DIRS = (
    '/path/to/your/sefaria/templates/',
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

EMAIL_HOST = 'localhost'
EMAIL_PORT = 1025
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

MONGO_HOST = "localhost"
# Name of the MongoDB database to use.
SEFARIA_DB = 'sefaria'
# Leave user and password blank if not using Mongo Auth
SEFARIA_DB_USER = 'sefaria'
SEFARIA_DB_PASSWORD = 'your mongo password'

# ElasticSearch server
SEARCH_HOST = "http://localhost:9200"
SEARCH_INDEX_ON_SAVE = True # Whether to send texts and source sheet to Search Host for indexing after save

SEFARIA_DATA_PATH = '/path/to/you/data/dir' # used for exporting texts 

GOOGLE_ANALYTICS_CODE = 'your google analytics code'

# Integration with a NationBuilder list
NATIONBUILDER = False
NATIONBUILDER_SLUG = ""
NATIONBUILDER_TOKEN = ""
NATIONBUILDER_CLIENT_ID = ""
NATIONBUILDER_CLIENT_SECRET = ""
