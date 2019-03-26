
# Dunamai

Dunamai is a Python 3.5+ library for producing dynamic version strings
compatible with [PEP 440](https://www.python.org/dev/peps/pep-0440).

## Usage

Install with `pip install dunamai`, and then use as a library:

```python
from dunamai import Version

# Assume that `git describe --tags --long --dirty`
# outputs `v0.1.0rc5-44-g644252b-dirty`.
version = Version.from_git_describe(flag_dirty=True)

assert version.serialize() == "0.1.0.post44.dev0+g644252b.dirty"
assert version.base == "0.1.0"
assert version.epoch is None
assert version.pre_type == "rc"
assert version.pre_number == 5
assert version.post == 44
assert version.dev == 0
assert version.commit == "g644252b"
assert version.dirty
```

The `serialize()` method gives you an opinionated, PEP 440-compliant default
that ensures that prerelease/postrelease/development versions are compatible
with Pip's `--pre` flag. The individual parts of the version are also available
for you to use and inspect as you please.

## Comparison to Versioneer

[Versioneer](https://github.com/warner/python-versioneer) is another great
library for dynamic versions, but there are some design decisions that
prompted the creation of Dunamai as an alternative:

* Versioneer has a CLI that generates Python code which needs to be committed
  into your repository, whereas Dunamai is just a normal importable library.
* Versioneer produces the version as an opaque string, whereas Dunamai provides
  a Version class with discrete parts that can then be inspected and serialized
  separately.
* Versioneer provides customizability through a config file, whereas Dunamai
  aims to offer customizability through its library API for scripting support
  and use in other libraries.

## Integration

* Setting a `__version__`:

  ```python
  import dunamai as _dunamai
  __version__ = _dunamai.get_version("your-library", third_choice=_dunamai.Version.from_git_describe).serialize()
  ```

* setup.py:

  ```python
  from setuptools import setup
  from dunamai import Version

  setup(
      name="your-library",
      version=Version.from_git_describe().serialize(),
  )
  ```

* [Poetry](https://poetry.eustace.io):

  ```python
  import subprocess
  from dunamai import Version

  version = Version.from_git_describe()
  subprocess.run("poetry run version {}".format(version))
  ```

  Or as an [Invoke](https://www.pyinvoke.org) task:

  ```python
  from invoke import task
  from dunamai import Version

  @task
  def set_version(ctx):
      version = Version.from_git_describe()
      ctx.run("poetry run version {}".format(version))
  ```

## Development

This project is managed using Poetry. After cloning the repository, run:

```
poetry install
poetry run pre-commit install
```

Run unit tests:

```
poetry run pytest --cov
poetry run tox
```
