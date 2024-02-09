
# Dunamai
Dunamai is a Python 3.5+ library and command line tool for producing dynamic,
standards-compliant version strings, derived from tags in your version control system.
This facilitates uniquely identifying nightly or per-commit builds in continuous integration
and releasing new versions of your software simply by creating a tag.

Dunamai is also available as a [GitHub Action](https://github.com/marketplace/actions/run-dunamai).

## Features
* Version control system support:
  * [Git](https://git-scm.com) (2.7.0+ is recommended, but versions as old as 1.8.2.3 will work with some reduced functionality)
  * [Mercurial](https://www.mercurial-scm.org)
  * [Darcs](http://darcs.net)
  * [Subversion](https://subversion.apache.org)
  * [Bazaar](https://bazaar.canonical.com/en)
  * [Fossil](https://www.fossil-scm.org/home/doc/trunk/www/index.wiki)
  * [Pijul](https://pijul.org)
* Version styles:
  * [PEP 440](https://www.python.org/dev/peps/pep-0440)
  * [Semantic Versioning](https://semver.org)
  * [Haskell Package Versioning Policy](https://pvp.haskell.org)
  * Custom output formats
* Can be used for projects written in any programming language.
  For Python, this means you do not need a setup.py.

## Usage
### Installation
```
pip install dunamai
```

### CLI
```console
# Suppose you are on commit g29045e8, 7 commits after the v0.2.0 tag.

# Auto-detect the version control system and generate a version:
$ dunamai from any
0.2.0.post7.dev0+g29045e8

# Or use an explicit VCS and style:
$ dunamai from git --no-metadata --style semver
0.2.0-post.7

# Custom formats:
$ dunamai from any --format "v{base}+{distance}.{commit}"
v0.2.0+7.g29045e8

# If you'd prefer to frame the version in terms of progress toward the next
# release rather than distance from the latest one, you can bump it:
$ dunamai from any --bump
0.2.1.dev7+g29045e8

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

### Library

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
that ensures that versions for untagged commits are compatible with Pip's `--pre` flag.
The individual parts of the version are also available for you to use and inspect as you please:

```python
assert version.base == "0.1.0"
assert version.stage == "rc"
assert version.revision == 5
assert version.distance == 44
assert version.commit == "g644252b"
assert version.dirty is True

# Available if the latest tag includes metadata, like v0.1.0+linux:
assert version.tagged_metadata == "linux"
```

### Tips
By default, the "v" prefix on the tag is required,
unless you specify a custom tag pattern.
You can either write a regular expression:

```console
$ dunamai from any --pattern "(?P<base>\d+\.\d+\.\d+)"
```

```python
from dunamai import Version

version = Version.from_any_vcs(pattern=r"(?P<base>\d+\.\d+\.\d+)")
```

...or use a named preset:

```console
$ dunamai from any --pattern default-unprefixed
```

```python
from dunamai import Version, Pattern

version = Version.from_any_vcs(pattern=Pattern.DefaultUnprefixed)
```

### VCS archives
Sometimes, you may only have access to an archive of a repository (e.g., a zip file) without the full history.
Dunamai can still detect a version in some of these cases:

* For Git, you can configure `git archive` to produce a file with some metadata for Dunamai.

  Add a `.git_archival.json` file to the root of your repository with this content:
  ```
  {
    "hash-full": "$Format:%H$",
    "hash-short": "$Format:%h$",
    "timestamp": "$Format:%cI$",
    "refs": "$Format:%D$",
    "describe": "$Format:%(describe:tags=true,match=v[0-9]*)$"
  }
  ```

  Add this line to your `.gitattributes` file.
  If you don't already have this file, add it to the root of your repository:
  ```
  .git_archival.json  export-subst
  ```

* For Mercurial, Dunamai will detect and use an `.hg_archival.txt` file created by `hg archive`.
  It will also recognize `.hgtags` if present.

### Custom formats
Here are the available substitutions for custom formats.
If you have a tag like `v9!0.1.2-beta.3+other`, then:

* `{base}` = `0.1.2`
* `{stage}` = `beta`
* `{revision}` = `3`
* `{distance}` is the number of commits since the last
* `{commit}` is the commit hash (defaults to short form, unless you use `--full-commit`)
* `{dirty}` expands to either "dirty" or "clean" if you have uncommitted modified files
* `{tagged_metadata}` = `other`
* `{epoch}` = `9`
* `{branch}` = `feature/foo`
* `{branch_escaped}` = `featurefoo`
* `{timestamp}` is in the format `YYYYmmddHHMMSS` as UTC

If you specify a substitution, its value will always be included in the output.
For conditional formatting, you can do something like this (Bash):

```bash
distance=$(dunamai from any --format "{distance}")
if [ "$distance" = "0" ]; then
    dunamai from any --format "v{base}"
else
    dunamai from any --format "v{base}+{distance}.{dirty}"
fi
```

## Comparison to Versioneer
[Versioneer](https://github.com/warner/python-versioneer)
is another great library for dynamic versions,
but there are some design decisions that prompted the creation of Dunamai as an alternative:

* Versioneer requires a setup.py file to exist, or else `versioneer install` will fail,
  rendering it incompatible with non-setuptools-based projects such as those using Poetry or Flit.
  Dunamai can be used regardless of the project's build system.
* Versioneer has a CLI that generates Python code which needs to be committed into your repository,
  whereas Dunamai is just a normal importable library
  with an optional CLI to help statically include your version string.
* Versioneer produces the version as an opaque string,
  whereas Dunamai provides a Version class with discrete parts
  that can then be inspected and serialized separately.
* Versioneer provides customizability through a config file,
  whereas Dunamai aims to offer customizability through its library API and CLI
  for both scripting support and use in other libraries.

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

  Or you can use the [poetry-dynamic-versioning](https://github.com/mtkennerly/poetry-dynamic-versioning) plugin.

## Other notes
* Dunamai needs access to the full version history to find tags and compute distance.
  Be careful if your CI system does a shallow clone by default.

  * For GitHub workflows, invoke `actions/checkout@v3` with `fetch-depth: 0`.
  * For GitLab pipelines, set the `GIT_DEPTH` variable to 0.
  * For Docker builds, copy the VCS history (e.g., `.git` folder) into the container.

  For Git, you can also avoid doing a full clone by specifying a remote branch for tags
  (e.g., `--tag-branch remotes/origin/master`).
* When using Git, remember that lightweight tags do not store their creation time.
  Therefore, if a commit has multiple lightweight tags,
  we cannot reliably determine which one should be considered the newest.
  The solution is to use annotated tags instead.
* When using Git, the initial commit must **not** be both tagged and empty
  (i.e., created with `--allow-empty`).
  This is related to a reporting issue in Git.
  For more info, [click here](https://github.com/mtkennerly/dunamai/issues/14).
