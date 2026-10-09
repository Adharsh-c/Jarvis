# JARVIS Laptop Agent

This folder is the secure local-agent boundary. The production implementation should:

1. Pair with the JARVIS server using a one-time token.
2. Accept only signed/authenticated requests.
3. Restrict all file paths to an approved workspace.
4. Validate commands against `policies/default-policy.yaml`.
5. Require server-side approval for sensitive actions.
6. Log every operation.
7. Support an emergency stop switch.
8. Never expose passwords, browser cookies, SSH keys, or personal directories.

Do not implement unrestricted shell execution or arbitrary remote-control behavior.
