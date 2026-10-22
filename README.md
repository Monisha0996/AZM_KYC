# AZM Markets | Dual-Portal KYC / AML Flask Demo

**Local demonstration using fictional data only. Not suitable for production or regulatory reliance.**

## Run on Windows

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

Demo users (change all passwords before deploying anywhere):

| Portal | Username | Password |
|---|---|---|
| Client | `client` | `Demo-client-2026!` |
| Compliance analyst | `analyst` | `Demo-analyst-2026!` |
| Senior manager | `manager` | `Demo-manager-2026!` |

Override demo credentials via `AZM_CLIENT_PASSWORD`, `AZM_ANALYST_PASSWORD`, and `AZM_MANAGER_PASSWORD` before first launch. Set `FLASK_SECRET_KEY` in the environment. Changing env passwords after initial DB creation does not update existing users.

## Portals

- **Client:** creates and edits own application, mandatory-question validation on submit, uploaded documents, suitability score, professional-investor request, FATCA / CRS declarations, acknowledgement and status report.
- **Compliance analyst:** views customer cases, conducts *manually entered* screening, source of funds checks, EDD and suggested deposit restrictions; downloads JSON.
- **Senior manager:** all compliance screens plus a recorded approval / rejection / request-information action. Approvals are blocked when the application is incomplete or compliance rules are unresolved.
- Clients cannot view internal screening, download internal JSON or record approval. User credentials are hashed, sessions are HTTP-only and state-changing forms use CSRF tokens. Uploads are not publicly served and have restricted extensions.

## Rules and gaps

Based on Individual Customer Onboarding – Compliance Version V4:
- Suitability: nine 1–3-point questions, threshold 18/27. Suitability and AML are independent.
- Ordinary versus requested professional classification; professional accreditation/employment evidence captured. **Questions 1–2 of professional classification are illegible in original document; these cannot safely establish eligibility.** Professional output is provisional and requires verification.
- FATCA / CRS declarations, unique tax jurisdictions with TIN or no-TIN reason.
- PEP -> EDD; Medium-High and High -> EDD and senior approval; High -> bank-origin first-deposit restriction, per supplied document.
- AML weights and thresholds are *illustrative*, awaiting signed-off Compliance matrix. FATCA US status should not be treated as suspicious by itself; replace demo factor with policy-compliant design.
- No live Sumsub, screening, country/sector risk feeds, tax validation, document authenticity checks, legal declaration, email, CRM sync, bank-deposit enforcement or trading account activation.

## Security warnings / production blockers

SQLite, unaudited authorization, local filesystem uploads, no virus scanner, no encryption-at-rest controls, no MFA, no retention/deletion workflow, no privacy notice, no production-ready consent wording, no rate limiting, no country/sector reference data, no actual Sumsub webhooks. These must be addressed with Compliance/security teams before use with customer information. Do not expose Flask's built-in development server to the internet.
