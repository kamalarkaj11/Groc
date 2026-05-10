"""Run the Django server with the appropriate WSGI server per platform."""

import os
import sys
import platform

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')


def main():
    if platform.system() == 'Windows':
        from waitress import serve
        from django.core.wsgi import get_wsgi_application
        application = get_wsgi_application()
        port = os.environ.get('PORT', '8000')
        print(f"Starting waitress on http://0.0.0.0:{port}")
        serve(application, host='0.0.0.0', port=port)
    else:
        from django.core.management import execute_from_command_line
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')
        execute_from_command_line(['gunicorn', 'grocery_store.wsgi:application', '--bind', '0.0.0.0:8000'])


if __name__ == '__main__':
    main()
