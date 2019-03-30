
## Unreleased

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
