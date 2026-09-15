from __future__ import annotations

import tkinter as tk
from tkinter import ttk


DARK_PALETTE = {
    "window": "#1B1C1F",
    "panel": "#222327",
    "elevated": "#292B30",
    "editor": "#18191C",
    "border": "#383B42",
    "text": "#E6E8EB",
    "muted": "#9297A0",
    "accent": "#5CAD72",
    "accent_active": "#70C185",
    "selection": "#35526F",
    "danger": "#D46A6A",
    "error": "#612F35",
    "row_alt": "#25272B",
}

UI_FONT = ("Microsoft YaHei UI", 9)
MONO_FONT = ("Cascadia Mono", 10)


def editor_options() -> dict[str, object]:
    return {
        "background": DARK_PALETTE["editor"],
        "foreground": DARK_PALETTE["text"],
        "insertbackground": DARK_PALETTE["text"],
        "selectbackground": DARK_PALETTE["selection"],
        "selectforeground": DARK_PALETTE["text"],
        "borderwidth": 0,
        "highlightthickness": 0,
        "font": MONO_FONT,
        "padx": 14,
        "pady": 12,
    }


def configure_dark_theme(root: tk.Misc) -> ttk.Style:
    palette = DARK_PALETTE
    root.configure(background=palette["window"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=palette["window"], foreground=palette["text"],
                    font=UI_FONT, bordercolor=palette["border"], darkcolor=palette["border"],
                    lightcolor=palette["border"], focuscolor=palette["accent"])
    style.configure("TFrame", background=palette["window"])
    style.configure("Panel.TFrame", background=palette["panel"])
    style.configure("Toolbar.TFrame", background=palette["panel"])
    style.configure("TLabel", background=palette["window"], foreground=palette["text"])
    style.configure("Title.TLabel", background=palette["panel"], foreground=palette["text"],
                    font=("Microsoft YaHei UI", 13, "bold"))
    style.configure("Muted.TLabel", background=palette["panel"], foreground=palette["muted"])
    style.configure("Status.TLabel", background=palette["panel"], foreground=palette["muted"],
                    padding=(10, 5))
    style.configure("TButton", background=palette["elevated"], foreground=palette["text"],
                    borderwidth=1, relief="flat", padding=(11, 6))
    style.map("TButton", background=[("active", palette["border"]),
                                      ("disabled", palette["panel"])],
              foreground=[("disabled", palette["muted"])])
    style.configure("Accent.TButton", background=palette["accent"], foreground="#101713",
                    borderwidth=0, padding=(14, 7), font=("Microsoft YaHei UI", 9, "bold"))
    style.map("Accent.TButton", background=[("active", palette["accent_active"]),
                                             ("disabled", palette["border"])])
    style.configure("Danger.TButton", foreground=palette["danger"])
    style.configure("TEntry", fieldbackground=palette["editor"], foreground=palette["text"],
                    insertcolor=palette["text"], padding=6)
    style.configure("TCombobox", fieldbackground=palette["editor"], foreground=palette["text"],
                    arrowcolor=palette["muted"], padding=5)
    style.map("TCombobox", fieldbackground=[("readonly", palette["editor"])],
              foreground=[("readonly", palette["text"])])
    style.configure("Treeview", background=palette["panel"], fieldbackground=palette["panel"],
                    foreground=palette["text"], rowheight=27, borderwidth=0)
    style.map("Treeview", background=[("selected", palette["selection"])],
              foreground=[("selected", palette["text"])])
    style.configure("Treeview.Heading", background=palette["elevated"],
                    foreground=palette["muted"], relief="flat", padding=(8, 7),
                    font=("Microsoft YaHei UI", 9, "bold"))
    style.map("Treeview.Heading", background=[("active", palette["border"])])
    style.configure("TNotebook", background=palette["window"], borderwidth=0, tabmargins=0)
    style.configure("TNotebook.Tab", background=palette["panel"], foreground=palette["muted"],
                    borderwidth=0, padding=(15, 8))
    style.map("TNotebook.Tab", background=[("selected", palette["elevated"])],
              foreground=[("selected", palette["text"]), ("active", palette["text"])])
    style.configure("TPanedwindow", background=palette["border"], sashwidth=1)
    style.configure("Vertical.TScrollbar", background=palette["elevated"],
                    troughcolor=palette["editor"], arrowcolor=palette["muted"], borderwidth=0)
    return style


def configure_closable_notebook(style: ttk.Style, root: tk.Misc) -> tuple[tk.PhotoImage, tk.PhotoImage]:
    normal = tk.PhotoImage(master=root, width=12, height=12)
    active = tk.PhotoImage(master=root, width=12, height=12)
    for image, color in ((normal, DARK_PALETTE["muted"]),
                         (active, DARK_PALETTE["text"])):
        for offset in range(3, 9):
            image.put(color, (offset, offset))
            image.put(color, (11 - offset, offset))
    style.element_create("close", "image", normal, ("active", active), border=4, sticky="")
    style.layout("Closable.TNotebook", style.layout("TNotebook"))
    style.layout("Closable.TNotebook.Tab", [
        ("Notebook.tab", {"sticky": "nswe", "children": [
            ("Notebook.padding", {"side": "top", "sticky": "nswe", "children": [
                ("Notebook.label", {"side": "left", "sticky": ""}),
                ("close", {"side": "left", "sticky": "", "expand": False}),
            ]}),
        ]}),
    ])
    style.configure("Closable.TNotebook", background=DARK_PALETTE["window"], borderwidth=0)
    style.configure("Closable.TNotebook.Tab", background=DARK_PALETTE["panel"],
                    foreground=DARK_PALETTE["muted"], borderwidth=0, padding=(15, 8))
    style.map("Closable.TNotebook.Tab", background=[("selected", DARK_PALETTE["elevated"])],
              foreground=[("selected", DARK_PALETTE["text"]),
                          ("active", DARK_PALETTE["text"])])
    return normal, active
