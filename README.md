# NGO Fund Platform Backend

Django REST Framework backend for the Rwanda Paediatric Association NGO Fund Platform.

## Stack

- Django
- Django REST Framework
- PostgreSQL
- Simple JWT
- django-filter
- drf-spectacular OpenAPI docs

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## API

- Auth login: `POST /api/auth/login/`
- Auth register: `POST /api/auth/register/`
- Auth refresh: `POST /api/auth/refresh/`
- Profile: `/api/auth/profile/`
- API root: `/api/`
- OpenAPI schema: `/api/schema/`
- Swagger docs: `/api/docs/`

## Implemented Domains

- Users, roles, profile, notifications, system settings
- Donors and donor communications
- Grants, projects, and budget lines
- Requisitions and approval/rejection actions
- Transactions and reconciliation action
- Reports
- Audit logs and documents
- Compliance checklist verification
- Staff requirements and sign-off
- Test cases and UAT feedback
