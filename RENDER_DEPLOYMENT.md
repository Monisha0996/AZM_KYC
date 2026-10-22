# AZM Markets KYC — GitHub + Render demo deployment

**DEMO ONLY:** This is NOT suitable for real KYC or identity documents. SQLite on Render free-tier service is ephemeral; real onboarding requires production-grade database, encrypted object storage, authorization, audit controls, policies, and applicable data residency review.

## Upload to GitHub
1. Create a **private** GitHub repository named `azm-kyc-demo`.
2. Extract ZIP. Upload the **contents of `azm_kyc_flask/`** to repository root (including `app.py`, `requirements.txt`, `templates/` and `.gitignore`). Do NOT upload SQLite databases, uploads, `.env`, or actual customer information.
3. Commit changes.

## Configure Render
1. Dashboard > New > Web Service > connect GitHub repo.
2. Language: Python 3; Branch: main; Root Directory: blank (if you uploaded contents to root).
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn --workers 1 --threads 4 --bind 0.0.0.0:$PORT app:app`
5. Under Environment set: `FLASK_SECRET_KEY`, `AZM_CLIENT_PASSWORD`, `AZM_ANALYST_PASSWORD`, `AZM_MANAGER_PASSWORD`. Use unique random secrets. Set these **before** the first deploy.
6. Health check path: `/healthz` (if supported in service settings).
7. Deploy. Login via `/login`.

### Persisting demo data (optional paid Render disk)
For demo persistence only, mount a Render disk at `/var/data` and add `AZM_DATA_DIR=/var/data`. This retains SQLite and uploads through deploys, but does not make the application production safe. Without a disk, user data is temporary and can disappear at any redeploy/restart.

### Problems
- `ModuleNotFoundError: gunicorn`: ensure updated requirements file is pushed.
- `Application exited`: verify four environment variables and Render logs.
- `gunicorn: command not found`: correct build command and language Python.
- `TemplateNotFound`: include templates directory and set Root Directory correctly.
- All demo data disappeared: no persistent storage was configured.
- `403`: your session is invalid or role does not permit this action; login again.

**Important:** Existing local SQLite accounts keep their existing passwords: environment password changes do not reset passwords already stored in an existing database.
