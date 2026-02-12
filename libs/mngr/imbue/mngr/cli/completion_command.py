import click
from click.shell_completion import BashComplete
from click.shell_completion import FishComplete
from click.shell_completion import ZshComplete

_SHELL_CLASSES = {
    "bash": BashComplete,
    "zsh": ZshComplete,
    "fish": FishComplete,
}

_SETUP_INSTRUCTIONS = {
    "bash": 'Add this to ~/.bashrc:\n\n  eval "$(_MNGR_COMPLETE=bash_source mngr)"',
    "zsh": 'Add this to ~/.zshrc:\n\n  eval "$(_MNGR_COMPLETE=zsh_source mngr)"',
    "fish": "Save the output to ~/.config/fish/completions/mngr.fish:\n\n  _MNGR_COMPLETE=fish_source mngr > ~/.config/fish/completions/mngr.fish",
}


@click.command(name="completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion_command(shell: str) -> None:
    """Output shell completion script for mngr.

    Prints the shell-specific completion script to stdout. The script enables
    tab completion for mngr commands and agent names.

    \b
    Examples:
      mngr completion bash
      mngr completion zsh
      eval "$(mngr completion zsh)"
    """
    cls = _SHELL_CLASSES[shell]
    # Create a completion instance to generate the source script.
    # The cli and ctx_args are not used for source generation, only prog_name and complete_var.
    comp = cls(
        cli=click.Group("mngr"),
        ctx_args={},
        prog_name="mngr",
        complete_var="_MNGR_COMPLETE",
    )
    source = comp.source()
    click.echo(source)
    click.echo(f"\n# Setup instructions:\n# {_SETUP_INSTRUCTIONS[shell]}", err=True)
