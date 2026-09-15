from database_system.gui.theme import DARK_PALETTE, editor_options


def test_dark_palette_has_clear_surface_and_accent_hierarchy() -> None:
    assert DARK_PALETTE["window"] != DARK_PALETTE["panel"]
    assert DARK_PALETTE["panel"] != DARK_PALETTE["elevated"]
    assert DARK_PALETTE["accent"] == "#5CAD72"
    assert DARK_PALETTE["text"] != DARK_PALETTE["muted"]


def test_editor_options_are_dark_and_borderless() -> None:
    options = editor_options()

    assert options["background"] == DARK_PALETTE["editor"]
    assert options["foreground"] == DARK_PALETTE["text"]
    assert options["insertbackground"] == DARK_PALETTE["text"]
    assert options["borderwidth"] == 0
    assert options["highlightthickness"] == 0
