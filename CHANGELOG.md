## Unreleased

* Fixed an issue with Git annotated tag sorting. When there was a newer
  annotated tag A on an older commit and an older annotated tag B on a
  newer commit, Dunamai would choose tag A, but will now correctly choose
  tag B because the commit is newer.

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
