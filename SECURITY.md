# Security Policy

Voice Memo Hub handles private audio, transcripts, and workflow intent. Treat
runtime data as sensitive.

## Supported Versions

| Version | Supported |
| --- | --- |
| 0.1.x alpha | Security reports accepted |

## Reporting A Vulnerability

Please open a private security advisory on GitHub if available, or contact the
maintainer directly before publishing details.

Do not include raw audio, transcripts, tokens, or private runtime
databases in public issues.

## Runtime Secrets

The project does not require committed secrets. Notification credentials,
external service credentials, policy files, raw audio, transcripts, logs, and
SQLite databases should live outside the repository under runtime configuration.
