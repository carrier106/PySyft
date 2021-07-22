# stdlib
import io

# third party
import click
import rich

# relative
from .deps import check_deps
from .lib import is_editable_mode


class RichGroup(click.Group):
    def format_usage(self, ctx, formatter):
        DEPENDENCIES = check_deps()
        sio = io.StringIO()
        console = rich.get_console()
        mode = ""
        if is_editable_mode():
            mode = "[bold red]EDITABLE DEV MODE[/bold red] :police_car_light:"
        console.print(
            f"[bold red]HA[/bold red][bold magenta]Grid[/bold magenta]!", ":mage:", mode
        )
        table = rich.table.Table()

        table.add_column("Dependency", style="magenta")
        table.add_column("Found", justify="right")

        for dep in sorted(DEPENDENCIES.keys()):
            path = DEPENDENCIES[dep]
            installed_str = ":white_check_mark:" if path is not None else ":cross_mark:"
            dep_emoji = ":gear:"
            if dep == "docker":
                dep_emoji = ":whale:"
            if dep == "git":
                dep_emoji = ":file_folder:"
            if dep == "virtualbox":
                dep_emoji = ":ballot_box_with_ballot: "
            if dep == "vagrant":
                dep_emoji = ":person_mountain_biking:"
            if dep == "ansible-playbook":
                dep_emoji = ":blue_book:"
            table.add_row(f"{dep_emoji} {dep}", installed_str)
            # console.print(dep_emoji, dep, installed_str)
        console.print(table)
        console.print("Usage: hagrid [OPTIONS] COMMAND [ARGS]...")
        formatter.write(sio.getvalue())
