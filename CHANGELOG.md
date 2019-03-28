
## Unreleased

* Renamed `Version.from_git_describe` to `Version.from_git`.
* Changed behavior of `Version.serialize` argument `with_metadata` so that,
  by default, metadata is excluded when post and dev are not set.
* Added `with_dirty` argument to `Version.serialize` and removed `flag_dirty`
  argument from `Version.from_git`. The information should always be collected,
  and it is up to the serialization step to decide what to do with it.
* Added `Version.from_detected_vcs`.

## v0.2.0 (2019-03-26)

* Fixed a wrong Git command being used.
* Made metadata serialization opt-in.

## v0.1.0 (2019-03-26)

* Initial release.
