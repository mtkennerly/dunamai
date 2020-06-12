from argparse import Namespace

import pytest

from dunamai import _run_cmd
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
        latest_tag=False,
        tag_dir="tags",
        debug=False,
    )
    assert parse_args(["from", "git"]).vcs == "git"
    assert parse_args(["from", "mercurial"]).vcs == "mercurial"
    assert parse_args(["from", "darcs"]).vcs == "darcs"
    assert parse_args(["from", "subversion"]).vcs == "subversion"
    assert parse_args(["from", "subversion"]).tag_dir == "tags"
    assert parse_args(["from", "bazaar"]).vcs == "bazaar"
    assert parse_args(["from", "fossil"]).vcs == "fossil"
    assert parse_args(["from", "any", "--pattern", r"\d+"]).pattern == r"\d+"
    assert parse_args(["from", "any", "--metadata"]).metadata is True
    assert parse_args(["from", "any", "--no-metadata"]).metadata is False
    assert parse_args(["from", "any", "--dirty"]).dirty is True
    assert parse_args(["from", "any", "--format", "v{base}"]).format == "v{base}"
    assert parse_args(["from", "any", "--style", "pep440"]).style == "pep440"
    assert parse_args(["from", "any", "--style", "semver"]).style == "semver"
    assert parse_args(["from", "any", "--latest-tag"]).latest_tag is True
    assert parse_args(["from", "any", "--tag-dir", "foo"]).tag_dir == "foo"
    assert parse_args(["from", "any", "--debug"]).debug is True
    assert parse_args(["from", "subversion", "--tag-dir", "foo"]).tag_dir == "foo"

    with pytest.raises(SystemExit):
        parse_args(["from", "unknown"])


def test__parse_args__check():
    assert parse_args(["check", "0.1.0"]) == Namespace(
        command="check", version="0.1.0", style="pep440"
    )
    assert parse_args(["check", "0.1.0", "--style", "semver"]).style == "semver"
    assert parse_args(["check", "0.1.0", "--style", "pvp"]).style == "pvp"

    with pytest.raises(SystemExit):
        parse_args(["check", "0.1.0", "--style", "unknown"])


def test__cli_check():
    _run_cmd("dunamai check 0.01.0")
    _run_cmd("dunamai check v0.1.0", codes=[1])
    _run_cmd("dunamai check 0.01.0 --style semver", codes=[1])
    _run_cmd("dunamai check", codes=[1])
    _run_cmd("echo 0.01.0 | dunamai check", shell=True)
