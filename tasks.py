import shlex
import shutil
from pathlib import Path

from invoke import task

ROOT = Path(__file__).parent


def get_version() -> str:
    for line in (ROOT / "pyproject.toml").read_text("utf-8").splitlines():
        if line.startswith("version ="):
            return line.replace("version = ", "").strip('"')

    return "0.0.0"


@task
def install(ctx):
    ctx.run("pip uninstall -y dunamai")
    shutil.rmtree("dist", ignore_errors=True)
    ctx.run("poetry build")
    wheel = next(ROOT.glob("dist/*.whl"))
    ctx.run('pip install "{}"'.format(wheel))


@task
def docs(ctx):
    version = get_version()
    manpage = "docs/dunamai.1"

    args = [
        "poetry",
        "run",
        "argparse-manpage",
        "--pyfile",
        "dunamai/__main__.py",
        "--function",
        "get_parser",
        "--project-name",
        "dunamai",
        "--prog",
        "dunamai",
        "--version",
        version,
        "--author",
        '"Matthew T. Kennerly (mtkennerly)"',
        "--url",
        "https://github.com/mtkennerly/dunamai",
        "--format",
        "single-commands-section",
        "--output",
        manpage,
        "--manual-title",
        "Dunamai",
    ]
    ctx.run(shlex.join(args))
