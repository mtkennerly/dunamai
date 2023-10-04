from argparse import Namespace

import pytest

from dunamai import _run_cmd
from dunamai.__main__ import parse_args, VERSION_SOURCE_PATTERN


def test__parse_args__from():
    assert parse_args(["from", "any"]) == Namespace(
        command="from",
        vcs="any",
        pattern=VERSION_SOURCE_PATTERN,
        dirty=False,
        metadata=None,
        format=None,
        style=None,
        latest_tag=False,
        tag_dir="tags",
        debug=False,
        bump=False,
        tagged_metadata=False,
        tag_branch=None,
        full_commit=False,
        strict=False,
        path=None,
    )
    assert parse_args(["from", "git"]).vcs == "git"
    assert parse_args(["from", "git", "--tag-branch", "foo"]).tag_branch == "foo"
    assert parse_args(["from", "git", "--full-commit"]).full_commit is True
    assert parse_args(["from", "mercurial"]).vcs == "mercurial"
    assert parse_args(["from", "mercurial", "--full-commit"]).full_commit is True
    assert parse_args(["from", "darcs"]).vcs == "darcs"
    assert parse_args(["from", "subversion"]).vcs == "subversion"
    assert parse_args(["from", "subversion"]).tag_dir == "tags"
    assert parse_args(["from", "bazaar"]).vcs == "bazaar"
    assert parse_args(["from", "fossil"]).vcs == "fossil"
    assert parse_args(["from", "pijul"]).vcs == "pijul"
    assert parse_args(["from", "any", "--pattern", r"\d+"]).pattern == r"\d+"
    assert parse_args(["from", "any", "--metadata"]).metadata is True
    assert parse_args(["from", "any", "--no-metadata"]).metadata is False
    assert parse_args(["from", "any", "--dirty"]).dirty is True
    assert parse_args(["from", "any", "--format", "v{base}"]).format == "v{base}"
    assert parse_args(["from", "any", "--style", "pep440"]).style == "pep440"
    assert parse_args(["from", "any", "--style", "semver"]).style == "semver"
    assert parse_args(["from", "any", "--latest-tag"]).latest_tag is True
    assert parse_args(["from", "any", "--tag-dir", "foo"]).tag_dir == "foo"
    assert parse_args(["from", "any", "--tag-branch", "foo"]).tag_branch == "foo"
    assert parse_args(["from", "any", "--full-commit"]).full_commit is True
    assert parse_args(["from", "any", "--debug"]).debug is True
    assert parse_args(["from", "any", "--tagged-metadata"]).tagged_metadata is True
    assert parse_args(["from", "any", "--strict"]).strict is True
    assert parse_args(["from", "any", "--path", "/tmp"]).path == "/tmp"
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
    _run_cmd("dunamai check 0.01.0", where=None)
    _run_cmd("dunamai check v0.1.0", where=None, codes=[1])
    _run_cmd("dunamai check 0.01.0 --style semver", where=None, codes=[1])
    _run_cmd("dunamai check", where=None, codes=[1])
    _run_cmd("echo 0.01.0 | dunamai check", where=None, shell=True)
