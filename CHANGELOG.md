## v1.19.2 (2024-02-16)

* Fixed an exception when a Git repository had a broken ref.
  Git would print a warning that Dunamai failed to parse.

## v1.19.1 (2024-02-07)

* Relaxed Python bounds from `^3.5` to `>=3.5` since Python does not follow Semantic Versioning.
* Fixed some `git log` commands that did not include `-c log.showsignature=false`.
  ([Contributed by pdecat](https://github.com/mtkennerly/dunamai/pull/75))

## v1.19.0 (2023-10-04)

* Added a `--path` option to inspect a directory other than the current one.
  The `Version.from_*` methods now also take a `path` argument.

## v1.18.1 (2023-09-22)

* For Git 2.16+, `--decorate-refs=refs/tags/` is now specified for `git log`
  in case you've configured `log.excludeDecoration=refs/tags/`.

## v1.18.0 (2023-07-10)

* Added a `vcs` attribute to `Version` to indicate which VCS was detected.

## v1.17.0 (2023-05-19)

* The `from` command will print a warning for shallow Git repositories.
  This becomes an error with `--strict`.
* The `Version` class has a new `concerns` field to indicate warnings with the version.
  Right now, the only possibility is `Concern.ShallowRepository`.

## v1.16.1 (2023-05-13)

* Fixed outdated reference to `pkg_resources` in the docstring for `get_version`.
* `CHANGELOG.md` and `tests` are now included in sdists.

## v1.16.0 (2023-02-21)

* Updated `Version.parse` to better handle PEP 440 versions produced by Dunamai itself.
  Specifically, in `1.2.3.post4.dev5`, the post number becomes the distance and the dev number is ignored.
  In `1.2.3.dev5`, the dev number becomes the distance.
* Added `increment` argument to `bump_version` and `Version.bump`.
  ([Contributed by legendof-selda](https://github.com/mtkennerly/dunamai/pull/54))
* Fixed Git detection when there is a "dubious ownership" error.
  Previously, `from git` would report that it was not a Git project,
  and `from any` would report that it could not detect a VCS.
  Now, both commands report that there is dubious ownership.
* Improved error reporting for `from any` VCS detection.
  The error now specifies which VCSes were checked and which were not found to be installed.

## v1.15.0 (2022-12-02)

* Added compatibility with Git versions as old as 1.8.2.3.

## v1.14.1 (2022-11-15)

* Fixed Git 2.7.0 compatibility by changing `git log --no-show-signature` to `git -c log.showsignature=false log`.

## v1.14.0 (2022-11-07)

* Added a `strict` option to prevent falling back to `0.0.0` when there are no tags.
* Added support for `.git_archival.json` files created by `git archive`.
* Added support for `.hg_archival.txt` files created by `hg archive`.

## v1.13.2 (2022-10-14)

* Fixed an error when parsing Git output with `showSignature = true` configured.
  ([Contributed by riton](https://github.com/mtkennerly/dunamai/pull/51))

## v1.13.1 (2022-09-25)

* Made pattern-related error messages more readable by moving the pattern after
  the primary message instead of mixing them.

## v1.13.0 (2022-08-21)

* Added support for [Pijul](https://pijul.org).

## v1.12.0 (2022-05-07)

* Added `Pattern` type for named pattern presets. Currently, this includes:
  * `Pattern.Default` (CLI: `--pattern default`) for the existing default.
  * `Pattern.DefaultUnprefixed` (CLI: `--pattern default-unprefixed`)
    for the existing default, but without requiring the `v` prefix.
* Added `tag_branch` option (CLI: `--tag-branch`) for Git repositories.
  This is particularly useful for Gitflow without fast forward, where
  `develop` does not contain the tag history, so you can specify
  `--tag-branch master`.
* Added `full_commit` option (CLI: `--full-commit`) for Git and Mercurial repositories
  to obtain the full commit hash instead of the short form.
* Fixed `Version.parse` so that it better handles versions without the `v`
  prefix when the pattern does not (or may not) require it.
* Fixed error reporting when a custom pattern is an invalid regular expression,
  as well as when a custom format is malformed.
  It was fine when Dunamai was used as a library, but the error message lacked
  context on the CLI.
* Fixed `from any` not passing the `--tag-dir` option along for Subversion
  repositories.

## v1.11.1 (2022-04-05)

* Fixed the `--bump` CLI option and the `bump` argument of `Version.serialize`
  bumping even on a commit with a version tag. Now, no bumping occurs on such
  a commit.

## v1.11.0 (2022-03-15)

* Explicitly specified `Optional[...]` typing on arguments with a default of `None`.
  ([Contributed by jonathangreen](https://github.com/mtkennerly/dunamai/pull/44))
* Made `VERSION_SOURCE_PATTERN` public for consumption by other tools.

## v1.10.0 (2022-03-08)

* Added `branch` and `timestamp` to the `Version` class,
  along with associated format placeholders (`branch`, `branch_escaped`, `timestamp`).
  Branch info is not populated for Darcs and Subversion repositories.
* Fixed validation for PEP 440, where the local segment was allowed to contain any characters.
* Fixed validation for Semantic Versioning, where some segments were allowed to contain
  these additional characters:

  ```
  [ \ ] ^ _ `
  ```

## v1.9.0 (2022-02-20)

* Changed `Version.serialize`'s `format` argument to support passing a callback.
  ([Contributed by marnikow](https://github.com/mtkennerly/dunamai/pull/40))
* Added `ignore` option to `get_version()`.
  ([Contributed by marnikow](https://github.com/mtkennerly/dunamai/pull/39))
* Added `parser` option to `get_version()`.
* Added `Version.parse()`.
  ([Contributed by marnikow](https://github.com/mtkennerly/dunamai/pull/41))
* Added `Version.bump()`.
  ([Contributed by marnikow](https://github.com/mtkennerly/dunamai/pull/38))

## v1.8.0 (2022-01-27)

* Changed the build backend to poetry-core.
  ([Contributed by fabaff](https://github.com/mtkennerly/dunamai/pull/35))
* Clarified serialization options that are ignored when using a custom format.
* Relaxed dependency range of `importlib-metadata` for compatibility with Poetry.
* Added `epoch` to `Version` class, default tag pattern, and format placeholders.
* Fixed PEP 440 validation to allow multiple digits in the epoch.
* Improved parsing of optional pattern groups so that we don't stop checking at
  the first one that's omitted.
* Fixed handling of tags with `post`/`dev` stages so that they are serialized
  and bumped correctly when using PEP 440.

## v1.7.0 (2021-10-31)

* Broadened the default version tag pattern to allow more separator styles
  recognized in PEP 440 pre-normalized forms (`-`, `.`, and `_`).
* Enhanced `serialize_pep440()` to normalize the alternative prerelease names
  (`alpha` -> `a`, `beta` -> `b`, `c`/`pre`/`preview` -> `rc`) and
  capitalizations (`RC` -> `rc`, etc).
* Added a `py.typed` file for PEP-561.
  ([Contributed by wwuck](https://github.com/mtkennerly/dunamai/pull/25))
* Replaced `pkg_resources` dependency with `packaging` and `importlib_metadata`.
  ([Contributed by flying-sheep](https://github.com/mtkennerly/dunamai/pull/29))
* Added some missing public items to `__all__`.

## v1.6.0 (2021-08-09)

* Fixed an oversight where the default version tag pattern would only find
  tags with exactly three parts in the base (e.g., `v1.0.0` and `v1.2.3`).
  This is now relaxed so that `v1`, `v1.2.3.4`, and so on are also recognized.
* Added support for execution via `python -m dunamai`.
  ([Contributed by jstriebel](https://github.com/mtkennerly/dunamai/pull/19))

## v1.5.5 (2021-04-26)

* Fixed handling of Git tags that contain slashes.
  ([Contributed by ioben](https://github.com/mtkennerly/dunamai/pull/17))

## v1.5.4 (2021-01-20)

* Fixed handling of Git tags that contain commas.

## v1.5.3 (2021-01-13)

* Fixed Semantic Versioning enforcement to allow metadata segments with
  more than two dot-separated identifiers.

## v1.5.2 (2020-12-17)

* For Git, avoided use of `--decorate-refs` to maintain compatibility with
  older Git versions.

## v1.5.1 (2020-12-16)

* Improved ordering of Git tags, particularly when commit dates were not chronological.
  ([Contributed by mariusvniekerk](https://github.com/mtkennerly/dunamai/pull/9))
* Improved Subversion handling when in a subdirectory of the repository.
  ([Contributed by Spirotot](https://github.com/mtkennerly/dunamai/pull/10))

## v1.5.0 (2020-12-02)

* Added the `--tagged-metadata` option and corresponding attribute on the
  `Version` class.
  ([Contributed by mariusvniekerk](https://github.com/mtkennerly/dunamai/pull/8))
* Added explicit dependency on setuptools (because of using `pkg_resources`)
  for environments where it is not installed by default.

## v1.4.1 (2020-11-17)

* For Git, replaced `--porcelain=v1` with `--porcelain` to maintain compatibility
  with older Git versions.

## v1.4.0 (2020-11-17)

* Added the `--bump` command line option and the `bump` argument to
  `Version.serialize()`.
* Fixed an issue with Git annotated tag sorting. When there was a newer
  annotated tag A on an older commit and an older annotated tag B on a
  newer commit, Dunamai would choose tag A, but will now correctly choose
  tag B because the commit is newer.
* With Git, trigger the dirty flag when there are untracked files.
  ([Contributed by jpc4242](https://github.com/mtkennerly/dunamai/pull/6))

## v1.3.1 (2020-09-27)

* Fixed ambiguous reference error when using Git if a tag and branch name
  were identical.

## v1.3.0 (2020-07-04)

* Previously, when there were not yet any version-like tags, the distance would
  be set to 0, so the only differentiator was the commit ID. Now, the distance
  will be set to the number of commits so far. For example:

  * No commits: base = 0.0.0, distance = 0
  * 1 commit, no tags: base = 0.0.0, distance = 1
  * 10 commits, no tags: base = 0.0.0, distance = 10

## v1.2.0 (2020-06-12)

* Added `--debug` flag.

## v1.1.0 (2020-03-22)

* Added these functions to the public API:
  * `serialize_pep440`
  * `serialize_semver`
  * `serialize_pvp`
  * `bump_version`

## v1.0.0 (2019-10-26)

* Changed the `Version` class to align with Dunamai's own semantics instead of
  PEP 440's semantics.

  Previously, `Version` implemented all of PEP 440's features, like epochs and
  dev releases, even though Dunamai itself did not use epochs (unless you
  created your own `Version` instance with one and serialized it) and always
  set dev to 0 in the `from_git`/etc methods. The `serialize` method then
  tried to generalize those PEP 440 concepts to other versioning schemes,
  as in `0.1.0-epoch.1` for Semantic Versioning, even though that doesn't
  have an equivalent meaning in that scheme.

  Now, the `Version` class implements the semantics used by Dunamai, giving
  it more power in the serialization to map those concepts in an appropriate
  way for each scheme. For example, `dev0` is now only added for PEP 440 (in
  order to be compatible with Pip's `--pre` flag), but `dev.0` is no longer
  added for Semantic Versioning because it served no purpose there.

  API changes:

  * `post` has been renamed to `distance`, and its type is simply `int`
    rather than `Optional[int]`
  * `epoch` and `dev` have been removed
  * `pre_type` has been renamed to `stage`
  * `pre_number` has been renamed to `revision`, and it is no longer required
    when specifying a stage
* Improved error reporting when the version control system cannot be detected
  and when a specified VCS is unavailable.
* Improved the default regular expression for tags:
  * It now requires a full match of the tag.
  * It now recognizes when the `base` and `stage` are separated by a hyphen.
  * It now recognizes when the `stage` and `revision` are separated by a dot.
  * It now allows a `stage` without a `revision`.

## v0.9.0 (2019-10-22)

* Added Fossil support.
* Fixed case with Git/Mercurial/Subversion/Bazaar where, if you checked out an
  older commit, then Dunamai would consider tags for commits both before and
  after the commit that was checked out. It now only considers tags for the
  checked out commit or one of its ancestors, making the results more
  deterministic.
* Changed VCS detection to be based on the result of VCS commands rather than
  looking for VCS-specific directories/files. This avoids the risk of false
  positives and simplifies cases with inconsistent VCS files (e.g.,
  Fossil uses `.fslckout` on Linux and `_FOSSIL_` on Windows)

## v0.8.1 (2019-08-30)

* Fixed handling of annotated Git tags, which were previously ignored.

## v0.8.0 (2019-06-05)

* Changed `Version.from_any_vcs` to accept the `tag_dir` argument,
  which will only be used if Subversion is the detected VCS.
  Likewise, `dunamai from any` now accepts `--tag-dir`.
* Added `Version.from_vcs` to make it easier for other tools to map from a
  user's VCS configuration to the appropriate function.

## v0.7.1 (2019-05-16)

* Fixed issue on Linux where shell commands were not interpreted correctly.

## v0.7.0 (2019-04-16)

* Added Bazaar support.
* Added the `dunamai check` command and the corresponding `check_version`
  function.
* Added the option to check just the latest tag or to keep checking tags
  until a match is found. The default behavior is now to keep checking.
* Added enforcement of Semantic Versioning rule against numeric segments
  with a leading zero.
* Renamed the `with_metadata` and `with_dirty` arguments of `Version.serialize`
  to `metadata` and `dirty` respectively.
* Fixed the equality and ordering of `Version` to consider all attributes.
  `dirty` and `commit` were ignored previously if neither `post` nor `dev`
  were set, and `dirty=None` and `dirty=False` were not distinguished.

## v0.6.0 (2019-04-14)

* Added Subversion support.
* Added support for the PVP style.
* Changed the type of the `style` argument in `Version.serialize`
  from `str` to `Style`.

## v0.5.0 (2019-03-31)

* Added built-in Semantic Versioning output style in addition to PEP 440.
* Added style validation for custom output formats.
* Added Darcs support.

## v0.4.0 (2019-03-29)

* Added support for custom serialization formats.

## v0.3.0 (2019-03-29)

* Added Mercurial support.
* Added a CLI.
* Renamed `Version.from_git_describe` to `Version.from_git`.
* Changed behavior of `Version.serialize` argument `with_metadata` so that,
  by default, metadata is excluded when post and dev are not set.
* Added `with_dirty` argument to `Version.serialize` and removed `flag_dirty`
  argument from `Version.from_git`. The information should always be collected,
  and it is up to the serialization step to decide what to do with it.
* Added `Version.from_any_vcs`.
* Removed `source` attribute of `Version` since some VCSes may require multiple
  commands in conjunction and therefore not have a single source string.

## v0.2.0 (2019-03-26)

* Fixed a wrong Git command being used.
* Made metadata serialization opt-in.

## v0.1.0 (2019-03-26)

* Initial release.
