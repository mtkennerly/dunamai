from argparse import Namespace

from dunamai.__main__ import parse_args, _VERSION_PATTERN


def test__parse_args__from():
    assert parse_args(["from", "any"]) == Namespace(
        command="from",
        vcs="any",
        pattern=_VERSION_PATTERN,
        dirty=False,
        metadata=None,
        format=None,
        style=None,
    )
    assert parse_args(["from", "git"]).vcs == "git"
    assert parse_args(["from", "mercurial"]).vcs == "mercurial"
    assert parse_args(["from", "darcs"]).vcs == "darcs"
    assert parse_args(["from", "subversion"]).vcs == "subversion"
    assert parse_args(["from", "any", "--pattern", r"\d+"]).pattern == r"\d+"
    assert parse_args(["from", "any", "--metadata"]).metadata is True
    assert parse_args(["from", "any", "--no-metadata"]).metadata is False
    assert parse_args(["from", "any", "--dirty"]).dirty is True
    assert parse_args(["from", "any", "--format", "v{base}"]).format == "v{base}"
    assert parse_args(["from", "any", "--style", "pep440"]).style == "pep440"
    assert parse_args(["from", "any", "--style", "semver"]).style == "semver"
    assert parse_args(["from", "subversion", "--tag-dir", "foo"]).tag_dir == "foo"
