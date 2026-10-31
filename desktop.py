#!/usr/bin/env python3
"""Native macOS shell for Meeting Actions."""
from __future__ import annotations

import threading

import server
import webview
from webview.menu import Menu, MenuAction
from desktop_policy import install_policy


def run() -> None:
    owned = server.make_server(port=0)
    worker = threading.Thread(target=owned.serve_forever, name="meeting-commitments-http", daemon=True)
    origin = f"http://127.0.0.1:{owned.server_port}"
    window = None
    started = False

    def quit_app(_window=None):
        if window is not None:
            window.destroy()

    menu = [Menu("File", [MenuAction("Quit Meeting Actions", quit_app)])]
    try:
        worker.start()
        started = True
        install_policy(origin)
        window = webview.create_window("Meeting Actions", origin + "/?desktop=1", width=1120, height=760, min_size=(760, 560), menu=menu)
        webview.start()
    finally:
        if started:
            owned.shutdown()
        owned.server_close()
        if started:
            worker.join(timeout=3)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        import AppKit

        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_("Meeting Actions could not start")
        alert.setInformativeText_("The local app failed to open. Restart Meeting Actions and try again.")
        alert.addButtonWithTitle_("OK")
        alert.runModal()
        raise SystemExit(1)
