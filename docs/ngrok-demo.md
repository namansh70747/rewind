# Rewind ngrok demo

This mode serves the Rewind frontend, Google sign-in, PostgreSQL recordings and private execution jobs on one origin. Start it on loopback port 8870 and point the ngrok tunnel there. Use a separate demo PostgreSQL database. The current local server and Vercel viewer have independent entry points.

## Configure

- Use the stable HTTPS domain shown in the ngrok dashboard. Configure HTTP Basic Auth on the ngrok endpoint, with username `rewind` and a fresh 12-character password stored in an ngrok vault. Share the password through a private channel.
- Create a hosted Google Web application client with the exact redirect URI `https://YOUR-ASSIGNED-DOMAIN/auth/google/callback`. Use an External audience. The app requests `openid email`. Keep the existing localhost OAuth callback and client.
- In the demo terminal environment set `REWIND_PUBLIC_ORIGIN` to the assigned origin without a trailing slash. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` from that hosted client, and `DATABASE_URL` to the separate demo PostgreSQL connection. Set `REWIND_OPEN_SIGNUP=1` to let verified Google accounts register after passing the shared password prompt.
- Provider keys use `GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY` and `XAI_API_KEY`. Set `REWIND_DEMO_PROVIDER` and optionally `REWIND_DEMO_MODEL` to select the approved live script's only provider and model. The worker gives that key only to the capture process. Verification uses recorded responses offline.

## Run

From this isolated checkout, install the locked dependencies and start the app. Startup applies the hosted and job schemas to the configured database.

```powershell
uv sync --locked
uv run --locked python -m flightrecorder.product.demo --port 8870 --allow-open-signup
```

Start a second terminal with the authenticated ngrok agent. Use the actual assigned domain and your private traffic policy. Turn off request inspection so request metadata does not appear in an agent inspection session.

```powershell
ngrok http http://127.0.0.1:8870 --url https://YOUR-ASSIGNED-DOMAIN --traffic-policy-file PATH_TO_POLICY --inspect=false
```

A protected request to `/health` should return `ready: true`. An anonymous request should get the password challenge. The free ngrok interstitial may appear on the first browser visit.

## Verify the full demo

- From a clean browser on another device, pass the ngrok prompt, sign up using Google, sign out, and sign back in.
- Capture the approved ready and blocked release scripts, inspect their evidence, replay the blocked run three times, and compare both runs. Swap selections and repeat the comparison after refresh.
- Check provider catalogue access and verify one successful bounded live capture using the configured model. Import and export a reviewed bundle. Imported recordings can be inspected and compared.
- With a second Google account, confirm private recordings, job details, comparison, and export are inaccessible. Use an explicitly reviewed shared bundle if both accounts should see the same evidence.
- Restart the demo and confirm that recordings, sessions and completed jobs persist. A worker restart marks interrupted jobs failed with a retry message. Keep the demo app and tunnel running during the walkthrough.
