# Product context

## First principle

Every proposed commitment must keep a direct path to the words that support it.

## User and job

Consultants and small teams review a meeting transcript, check proposed actions and decisions, resolve owner or date questions, then export only the items they confirm.

## Data choice

Transcript text and review state live in a local SQLite database outside the source folder. The app starts with a fictional, labeled sample transcript. It sends no data off the device.

## Extraction contract

The local rule set recognizes a limited set of action and decision phrases. It keeps the original transcript line, speaker, timestamp, and text as evidence. Tentative language, possible date conflicts, and missing owners start unresolved. The user must edit and save an unresolved item before confirming it. Confirmation needs an owner. Export filters to confirmed items and includes evidence.

## Boundaries

This version accepts pasted text in `[HH:MM:SS] Speaker: words` format. It does not transcribe audio, connect to meeting services, send tasks, invitations, or messages, or claim that its rules catch every commitment.
