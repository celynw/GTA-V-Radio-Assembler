"""GTA V Radio Soundtrack Assembler."""

import typer

app = typer.Typer()


@app.command()
def main() -> None:
	"""Run GTA V Radio Soundtrack Assembler."""
	typer.echo("Hello!")


if __name__ == "__main__":
	app()
