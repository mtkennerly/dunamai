
# Dunamai
[![Version](https://img.shields.io/pypi/v/dunamai)](https://pypi.org/project/dunamai)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Dunamai is a Python 3.5+ library and command line tool for producing dynamic,
standards-compliant version strings, derived from tags in your version
control system. This facilitates uniquely identifying nightly or per-commit
builds in continuous integration and releasing new versions of your software
simply by creating a tag.

Dunamai is also available as a [GitHub Action](https://github.com/marketplace/actions/run-dunamai).

## Features
* Version control system support:
  * [Git](https://git-scm.com) (minimum version: 2.7.0)
  * [Mercurial](https://www.mercurial-scm.org)
  * [Darcs](http://darcs.net)
  * [Subversion](https://subversion.apache.org)
  * [Bazaar](https://bazaar.canonical.com/en)
  * [Fossil](https://www.fossil-scm.org/home/doc/trunk/www/index.wiki)
* Version styles:
  * [PEP 440](https://www.python.org/dev/peps/pep-0440)
  * [Semantic Versioning](https://semver.org)
  * [Haskell Package Versioning Policy](https://pvp.haskell.org)
  * Custom output formats
* Can be used for projects written in any programming language.
  For Python, this means you do not need a setup.py.

## Usage
Install with `pip install dunamai`, and then use as either a CLI:

```console
# Suppose you are on commit g29045e8, 7 commits after the v0.2.0 tag.
# Note that the "v" prefix on the tag is required, unless you specify
# a different tag style using "--pattern".

# Auto-detect the version control system and generate a version:
$ dunamai from any
0.2.0.post7.dev0+g29045e8

# Or use an explicit VCS and style:
$ dunamai from git --no-metadata --style semver
0.2.0-post.7

# Custom formats:
$ dunamai from any --format "v{base}+{distance}.{commit}"
v0.2.0+7.g29045e8

# Validation of custom formats:
$ dunamai from any --format "v{base}" --style pep440
Version 'v0.2.0' does not conform to the PEP 440 style

# Validate your own freeform versions:
$ dunamai check 0.01.0 --style semver
Version '0.01.0' does not conform to the Semantic Versioning style

# More info:
$ dunamai --help
$ dunamai from --help
$ dunamai from git --help
```

Or as a library:

```python
from dunamai import Version, Style

# Let's say you're on commit g644252b, which is tagged as v0.1.0.
version = Version.from_git()
assert version.serialize() == "0.1.0"

# Let's say there was a v0.1.0rc5 tag 44 commits ago
# and you have some uncommitted changes.
version = Version.from_any_vcs()
assert version.serialize() == "0.1.0rc5.post44.dev0+g644252b"
assert version.serialize(metadata=False) == "0.1.0rc5.post44.dev0"
assert version.serialize(dirty=True) == "0.1.0rc5.post44.dev0+g644252b.dirty"
assert version.serialize(style=Style.SemVer) == "0.1.0-rc.5.post.44+g644252b"
```

The `serialize()` method gives you an opinionated, PEP 440-compliant default
that ensures that versions for untagged commits are compatible with Pip's
`--pre` flag. The individual parts of the version are also available for you
to use and inspect as you please:

```python
assert version.base == "0.1.0"
assert version.stage == "rc"
assert version.revision == 5
assert version.distance == 44
assert version.commit == "g644252b"
assert version.dirty is True
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
  into your repository, whereas Dunamai is just a normal importable library
  with an optional CLI to help statically include your version string.
* Versioneer produces the version as an opaque string, whereas Dunamai provides
  a Version class with discrete parts that can then be inspected and serialized
  separately.
* Versioneer provides customizability through a config file, whereas Dunamai
  aims to offer customizability through its library API and CLI for both
  scripting support and use in other libraries.

## Integration
* Setting a `__version__` statically:

  ```console
  $ echo "__version__ = '$(dunamai from any)'" > your_library/_version.py
  ```
  ```python
  # your_library/__init__.py
  from your_library._version import __version__
  ```

  Or dynamically (but Dunamai becomes a runtime dependency):

  ```python
  # your_library/__init__.py
  import dunamai as _dunamai
  __version__ = _dunamai.get_version("your-library", third_choice=_dunamai.Version.from_any_vcs).serialize()
  ```

* setup.py (no install-time dependency on Dunamai as long as you use wheels):

  ```python
  from setuptools import setup
  from dunamai import Version

  setup(
      name="your-library",
      version=Version.from_any_vcs().serialize(),
  )
  ```

  Or you could use a static inclusion approach as in the prior example.

* [Poetry](https://poetry.eustace.io):

  ```console
  $ poetry version $(dunamai from any)
  ```

## Development
This project is managed using [Poetry](https://poetry.eustace.io).
Development requires Python 3.6+ because of [Black](https://github.com/ambv/black).

* If you want to take advantage of the default VSCode integration, then first
  configure Poetry to make its virtual environment in the repository:
  ```
  poetry config settings.virtualenvs.in-project true
  ```
* After cloning the repository, activate the tooling:
  ```
  poetry install
  poetry run pre-commit install
  ```
* Run unit tests:
  ```
  poetry run pytest --cov
  poetry run tox
  ```
