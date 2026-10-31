# Meeting Commitments

Turn a meeting transcript into a short list of proposed actions and decisions. Each proposal shows its original speaker and timestamp. It keeps the source words beside it. Review the owner and due date before you confirm or export a proposal.

This is a local review tool. It does not send tasks, invitations, or messages. Extraction uses simple, documented text rules. It is not an AI transcript reader. It may miss a commitment or suggest a line that is not one. Check every proposal against its source.

**Install and run on macOS**

The native app opens as a local Mac window. No browser tab or manual server start is needed. In this source folder, build and install it with:

```sh
python3.12 -m venv .desktop-venv
.desktop-venv/bin/python -m pip install -r requirements-desktop.lock.txt
.desktop-venv/bin/python build_desktop.py
.desktop-venv/bin/python install_desktop.py
```

Then open `~/Applications/Meeting Commitments.app` in Finder. Use File → Quit Meeting Commitments or close the window to stop the local listener. To remove only the marked app copy, run `.desktop-venv/bin/python uninstall_desktop.py`. Stored meeting data remains in `~/.local/share/meeting-commitments` until removed in Settings.

## Browser development

Requires Python 3.10 or later. No packages need to be installed.

```sh
python3 server.py
```

Open <http://127.0.0.1:8344>. The app binds only to loopback. On first run it creates a clearly labeled fictional sample meeting. Use it to try source highlighting, review, and export. Import your transcript to replace the selected meeting.

Use one transcript turn per line in this form:

```text
[00:00:12] Alex: I will send the draft by Friday.
```

## Review and export

The local rule extractor proposes lines with clear action or decision phrases. Tentative wording, possible date conflicts, and missing owners start unresolved. Save edits to mark a proposal as reviewed. Add an owner before you confirm it. A date can remain blank. Exports include confirmed items only. They keep their evidence references.

The transcript is stored as text in a local SQLite database. The default database path is `~/.local/share/meeting-commitments/commitments.sqlite3`. Set `MEETING_COMMITMENTS_DATA` before launch to choose another local data folder. Use Settings to delete stored meeting data.

## Checks

```sh
python3 -m unittest discover -s tests -v
```

Tests check source references and unresolved proposals. They also check confirmation rules, export filtering, local request boundaries, malformed inputs, and escaping user text.

## Limits

- The app supports pasted or typed transcripts in the line format above. It does not transcribe audio or read external files.
- Proposal extraction uses rules and recognizes only a small set of phrases. It may miss other proposals.
- The app uses no remote services, outbound integrations, accounts, or credentials.

## License

MIT. See [LICENSE](LICENSE).

For browser development, use the command and local address above. The native app targets macOS; other operating systems have not been tested.
