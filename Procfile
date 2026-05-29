web: cd backend && gunicorn breathe_esg.wsgi:application --bind 0.0.0.0:$PORT --workers 2
release: cd backend && python manage.py migrate && python manage.py seed_demo
