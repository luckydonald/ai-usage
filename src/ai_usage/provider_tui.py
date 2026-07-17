"""Textual choice screens used by provider-management commands."""

from dataclasses import dataclass

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option


@dataclass(frozen=True, slots=True)
class SelectionChoice:
    key: str
    label: str
    detail: str = ""
# end class


class SelectionApp(App[str | None]):
    CSS = """
    #title { padding: 1 2; text-style: bold; }
    #choices { height: 1fr; margin: 0 1; border: round $accent; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, choices: list[SelectionChoice]):
        super().__init__()
        self.selection_title = title
        self.choices = choices
    # end def

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(self.selection_title, id="title")
        yield OptionList(
            *(
                Option(
                    f"{choice.label}\n  {choice.detail}" if choice.detail else choice.label,
                    id=choice.key,
                )
                for choice in self.choices
            ),
            id="choices",
        )
        yield Footer()
    # end def

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.exit(event.option.id)
    # end def

    def action_cancel(self) -> None:
        self.exit(None)
    # end def
# end class


async def select_choice(title: str, choices: list[SelectionChoice]) -> str | None:
    if not choices:
        return None
    # end if
    return await SelectionApp(title, choices).run_async()
# end def
