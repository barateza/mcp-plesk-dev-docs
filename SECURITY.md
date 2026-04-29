# Security Policy

## Reporting Vulnerabilities

**DO NOT** open public GitHub issues for security flaws.
- **Email**: [advisory@barateza.org](mailto:advisory@barateza.org)
- **Telegram**: [@barateza](https://t.me/barateza)
- **Response**: We aim to respond within 48 hours.

## Security Guidelines

### For Users
- **Secure Access**: Restrict server access to trusted networks; enforce strict file permissions on the storage directory.
- **Dependencies**: Keep environment updated: `pip install --upgrade -r requirements.txt`.
- **Model Integrity**: Download ML models (~1GB) over HTTPS only.
- **Credentials**: Use SSH keys/PATs; never commit secrets to version control.

### For Developers
- **Input Validation**: Sanitize all inputs, validate file paths, and limit query sizes.
- **Secure Logging**: Do not log PII, credentials, or sensitive paths.
- **Dependency Audit**: Run `pip check` and keep Python 3.12+ current.

## Supported Versions
| Version | Status | Security Updates |
|---------|--------|------------------|
| 0.2.x   | Active | Yes              |
| 0.1.x   | Active | Yes              |

## Core Dependencies
Monitored for vulnerabilities: `sentence-transformers`, `lancedb`, `fastmcp`, `beautifulsoup4`, `gitpython`.
