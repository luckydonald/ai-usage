import pytest

from ai_usage.provider_tui import SelectionApp, SelectionChoice


@pytest.mark.asyncio
async def test_selection_app_returns_highlighted_choice() -> None:
    app = SelectionApp(
        "Choose an account",
        [SelectionChoice("first", "First"), SelectionChoice("second", "Second")],
    )

    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
    # end with

    assert app.return_value == "first"
# end def


@pytest.mark.asyncio
async def test_selection_app_can_cancel() -> None:
    app = SelectionApp("Choose an account", [SelectionChoice("first", "First")])

    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
    # end with

    assert app.return_value is None
# end def
