# Hosted release checklist

## Staging configuration

- Create a staging Vercel project and a separate managed PostgreSQL database. Use a stable HTTPS staging domain and a pooled runtime database URL. Configure REWIND_PUBLIC_ORIGIN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, DATABASE_URL and REWIND_ALLOWED_EMAILS in the staging project.
- In Google Cloud, configure a Web application OAuth client with the stable origin plus /auth/google/callback. Add both invited accounts as test users where required. For the demo use a separate OAuth client, Vercel environment and database.
- Install from the exact candidate with uv sync --locked. Run scripts/manage_hosted.py migrate once with the migration database credentials. Grant runtime access to the resulting tables. Publish only reviewed evidence with scripts/manage_hosted.py publish-demo PATH. Keep bundles and credential files outside the deployment package.
- Record the candidate Git SHA, previous compatible deployment, database backup, and the evidence for a restore tested on a separate copy.

## Candidate gates

- Check /health for the expected build SHA and readiness. Confirm Google signup, repeated signup, sign-out and returning sign-in on two laptops. Exercise cancelled consent, expired attempts and expired sessions.
- Confirm both accounts can inspect the reviewed demo collection. Import one private bundle per account and confirm direct inspection, comparison and export all deny cross-account access. Repeat signed out and with an uninvited account.
- Import, inspect, compare and export real reviewed evidence. Exercise invalid checksums, unsupported formats and oversized uploads. Check the UI at wide and narrow widths.
- Redeploy the same candidate, then verify recordings, demo access, and unexpired sessions persisted. Verify sign-out revokes the session. Confirm unavailable database and OAuth errors produce actionable screens. Restore a backup copy and rehearse rollback before promotion.
- Rehearse local capture, offline replay and explanation of the observed difference. Open the approved demo recording on the second laptop. Share the demo URL after these gates pass.

Vercel project credentials, databases, account invitations and approval evidence are environment-specific. Keep the local walkthrough ready while the hosted checks are pending.
