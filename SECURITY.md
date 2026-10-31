# Security

Meeting Actions reviews task candidates from transcript files. It keeps its database in an owner-only folder and checks the database and SQLite sidecar files after opening them. The app rejects unsafe runtime paths and fails if it cannot confirm private permissions. Local transcripts and tasks are plaintext; a hash would not make them private. Use made-up transcript lines in reports.

The native app has an ad-hoc code signature. This lets the installer check whether its files changed. It does not prove who made the app. The build is not notarized. Account permissions limit access. Use your Mac’s disk encryption to protect saved files.

Report security issues through [GitHub private vulnerability reporting](https://github.com/gmperkinsmba/meeting-actions/security/advisories/new).
