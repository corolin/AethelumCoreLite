# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.1.x   | :white_check_mark: |
| < 1.1.0 | :x:                |

## Security Design Principles

AethelumCoreLite enforces the following security boundaries by design:

- **WAL & Persistence Integrity**: Write-ahead log operations use strict LSN tracking and atomic state transitions to prevent data corruption or stale replay.
- **API Authentication**: Built-in HTTP/Metrics endpoints support Bearer token (`apiKey`) authentication.
- **Anti-Injection Audit Prompts**: Cryptographically random tokens and nonces (`AsyncLocalStorage`-bound) isolate audit verification from prompt-injection tampering.

## Reporting a Vulnerability

The AethelumCoreLite team takes security issues seriously. If you discover a security vulnerability in this project, please report it **privately**:

1. **GitHub Private Vulnerability Reporting (Recommended)**:  
   Navigate to the [Security Advisories](https://github.com/corolin/AethelumCoreLite/security/advisories/new) tab in this repository and click **"Report a vulnerability"**. This allows us to review and fix the issue before public disclosure.

2. **Direct Contact**:  
   If you cannot use GitHub Security Advisories, please contact the repository maintainer directly.

### What to include in your report:
- A clear description of the vulnerability and affected module (`core`, `wal`, `api`, `prompts`, etc.).
- Steps to reproduce or proof-of-concept (PoC) code.
- Potential impact and attack scenarios.
- Suggested mitigation (if any).

We will acknowledge receipt within 48 hours and work with you on a resolution and coordinated public disclosure.
