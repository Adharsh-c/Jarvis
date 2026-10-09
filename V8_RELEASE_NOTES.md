# JARVIS V8 Release Notes — Final Production Release

## Final-stage additions
- Production environment mode with startup validation for unsafe/default secrets.
- Trusted Host middleware in production.
- Security response headers.
- Optional API docs disabled in production.
- Production Windows startup script and health-check script.
- Explicit `.env.production.example`.
- Desktop action `capture_screen`, always approval-gated.
- Desktop emergency-stop endpoint and dashboard button.
- Pending desktop actions are atomically moved to `executing` when claimed by the laptop agent, reducing duplicate execution.
- Laptop agent stores captured screenshots only under the approved JARVIS workspace.
- Added Pillow to laptop-agent requirements for screen capture.
- Dashboard updated to expose the final desktop controls.

## Deployment boundary
V8 is deployable for a controlled Windows/LAN environment. It intentionally does not expose arbitrary remote shell, administrator operations, silent installation, Git push or public-Internet remote control.

## Verification
- Python compilation: backend and laptop-agent compile successfully.
- Release package excludes `.env`, virtual environments, database files and Python cache files.
