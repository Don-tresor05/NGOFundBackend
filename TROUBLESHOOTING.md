# Troubleshooting Guide

## "ModuleNotFoundError: No module named 'stripe'"

**Solution:**
The stripe package is already installed. Simply restart the Django development server:

```bash
# Stop the server (CTRL+C)
# Then restart it
source .venv/bin/activate
python manage.py runserver
```

The auto-reloader should detect the changes and restart automatically.

## Verify Installation

```bash
source .venv/bin/activate
python -c "import stripe; print('Stripe OK')"
python manage.py check
```

If both commands succeed, the server should start without errors.

## Common Issues

1. **Virtual environment not activated**
   - Solution: `source .venv/bin/activate`

2. **Package not installed**
   - Solution: `pip install stripe`

3. **Server cached old state**
   - Solution: Restart the server completely

---

**Status:** All packages installed correctly. Just restart the server.
