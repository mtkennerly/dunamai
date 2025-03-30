import datetime as dt
import re
import shutil
import sys
from pathlib import Path

from invoke import task

ROOT = Path(__file__).parent


def get_version() -> str:
    for line in (ROOT / "pyproject.toml").read_text("utf-8").splitlines():
        if line.startswith("version ="):
            return line.replace("version = ", "").strip('"')

    raise RuntimeError("Could not determine version")


def replace_pattern_in_file(file: Path, old: str, new: str, count: int = 1):
    content = file.read_text("utf-8")
    updated = re.sub(old, new, content, count=count)
    file.write_text(updated, "utf-8")


def confirm(prompt: str):
    response = input(f"Confirm by typing '{prompt}': ")
    if response.lower() != prompt.lower():
        sys.exit(1)


@task
def build(ctx, clean=True):
    with ctx.cd(ROOT):
        if clean:
            shutil.rmtree("dist", ignore_errors=True)
        ctx.run("poetry build")


@task
def install(ctx):
    ctx.run("pip uninstall -y dunamai")
    build(ctx)
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
        "Matthew T. Kennerly (mtkennerly)",
        "--url",
        "https://github.com/mtkennerly/dunamai",
        "--format",
        "single-commands-section",
        "--output",
        manpage,
        "--manual-title",
        "Dunamai",
    ]

    # Join manually to avoid issues with single quotes on Windows using `shlex.join`
    joined = " ".join(arg if " " not in arg else f'"{arg}"' for arg in args)

    ctx.run(joined)


@task
def prerelease(ctx, new_version):
    date = dt.datetime.now().strftime("%Y-%m-%d")

    replace_pattern_in_file(
        ROOT / "pyproject.toml",
        'version = ".+"',
        f'version = "{new_version}"',
    )

    replace_pattern_in_file(
        ROOT / "CHANGELOG.md",
        "## Unreleased",
        f"## v{new_version} ({date})",
    )

    build(ctx)
    docs(ctx)


@task
def release(ctx):
    version = get_version()

    confirm(f"release {version}")

    ctx.run(f'git commit -m "Release v{version}"')
    ctx.run(f'git tag v{version} -m "Release"')
    ctx.run("git push")
    ctx.run("git push origin tag v{version}")

    ctx.run("poetry publish")
