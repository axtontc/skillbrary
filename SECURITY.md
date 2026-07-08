# Security Policy

## Supported Versions

Currently, only the latest release on the `main` branch is supported with security updates. 

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| `< 1.0` | :x:                |

## Reporting a Vulnerability

We take the security of Skillbrary incredibly seriously. Because this toolkit orchestrates autonomous agent swarms that can execute sandboxed code, any vulnerability that allows for privilege escalation, sandbox escaping, or arbitrary execution is treated as a critical, severity-1 incident.

**DO NOT** report security vulnerabilities via public GitHub issues.

Instead, please email vulnerabilities directly to the maintainers or use GitHub's private vulnerability reporting feature.

Please include:
1. A description of the vulnerability.
2. The exact steps to reproduce it (a `repro.py` script is highly preferred).
3. The potential impact (e.g., "Allows an agent to escape the `runtime/sandbox.py` isolation").

We will acknowledge receipt of your vulnerability report within 48 hours and strive to issue a patch and security advisory as rapidly as possible.
