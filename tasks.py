import shutil
from pathlib import Path

from invoke import task

ROOT = Path(__file__).parent


@task
def install(ctx):
    ctx.run("pip uninstall -y dunamai")
    shutil.rmtree("dist", ignore_errors=True)
    ctx.run("poetry build")
    wheel = next(ROOT.glob("dist/*.whl"))
    ctx.run('pip install "{}"'.format(wheel))
