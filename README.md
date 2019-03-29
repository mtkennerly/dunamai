
# Dunamai

Dunamai is a Python 3.5+ library for producing dynamic version strings
compatible with [PEP 440](https://www.python.org/dev/peps/pep-0440).

## Features

* Supports non-setuptools-based projects, so no need for a setup.py.
* Version control system support:
  * Git
  * Mercurial

## Usage

Install with `pip install dunamai`, and then use as a library:

```python
from dunamai import Version

# If `git describe` says `v0.1.0` or `v0.1.0-0-g644252b`
version = Version.from_git()
assert version.serialize() == "0.1.0"

# Or if `git describe` says `v0.1.0rc5-44-g644252b-dirty`
version = Version.from_detected_vcs()
assert version.serialize() == "0.1.0rc5.post44.dev0+g644252b"
assert version.serialize(with_metadata=False) == "0.1.0rc5.post44.dev0"
assert version.serialize(with_dirty=True) == "0.1.0rc5.post44.dev0+g644252b.dirty"
```

The `serialize()` method gives you an opinionated, PEP 440-compliant default
that ensures that pre/post/development releases are compatible with Pip's
`--pre` flag. The individual parts of the version are also available for you
to use and inspect as you please:

```python
assert version.base == "0.1.0"
assert version.epoch is None
assert version.pre_type == "rc"
assert version.pre_number == 5
assert version.post == 44
assert version.dev == 0
assert version.commit == "g644252b"
assert version.dirty
```

## Comparison to Versioneer

[Versioneer](https://github.com/warner/python-versioneer) is another great
library for dynamic versions, but there are some design decisions that
prompted the creation of Dunamai as an alternative:

* Versioneer requires a setup.py file to exist, or else `versioneer install`
  will fail, rendering it incompatible with non-setuptools-based projects
  such as those using Poetry or Flit. Dunamai can be used regardless of the
  project's build system.
* Versioneer has a CLI that generates Python code which needs to be committed
  into your repository, whereas Dunamai is just a normal importable library.
* Versioneer produces the version as an opaque string, whereas Dunamai provides
  a Version class with discrete parts that can then be inspected and serialized
  separately.
* Versioneer provides customizability through a config file, whereas Dunamai
  aims to offer customizability through its library API for scripting support
  and use in other libraries.

## Integration

* Setting a `__version__` statically (sample [Invoke](https://www.pyinvoke.org) task):

  ```python
  # tasks.py
  from invoke import task
  from pathlib import Path
  from dunamai import Version

  @task
  def set_version(ctx):
      version = Version.from_detected_vcs()
      Path("your_library/_version.py").write_text("__version__ = '{}'".format(version))
  ```
  ```python
  # your_library/__init__.py
  from your_library._version import __version__
  ```

  Or dynamically (but Dunamai becomes a runtime dependency):

  ```python
  # your_library/__init__.py
  import dunamai as _dunamai
  __version__ = _dunamai.get_version("your-library", third_choice=_dunamai.Version.from_detected_vcs).serialize()
  ```

* setup.py (no install-time dependency on Dunamai as long as you use wheels):

  ```python
  from setuptools import setup
  from dunamai import Version

  setup(
      name="your-library",
      version=Version.from_detected_vcs().serialize(),
  )
  ```

  Or you could use a static inclusion approach as in the prior example.

* [Poetry](https://poetry.eustace.io) (sample [Invoke](https://www.pyinvoke.org) task):

  ```python
  # tasks.py
  from invoke import task
  from dunamai import Version

  @task
  def set_version(ctx):
      version = Version.from_detected_vcs()
      ctx.run("poetry version {}".format(version))
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
