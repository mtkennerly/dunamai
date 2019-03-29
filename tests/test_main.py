
from argparse import Namespace

from dunamai.__main__ import parse_args


def test__parse_args__from():
    assert parse_args(["from", "any"]) == Namespace(
        command="from", vcs="any", pattern=None, dirty=False, metadata=None,
    )
    assert parse_args(["from", "git"]) == Namespace(
        command="from", vcs="git", pattern=None, dirty=False, metadata=None,
    )
    assert parse_args(["from", "mercurial"]) == Namespace(
        command="from", vcs="mercurial", pattern=None, dirty=False, metadata=None,
    )

    assert parse_args(["from", "any", "--pattern", r"\d+"]) == Namespace(
        command="from", vcs="any", pattern=r"\d+", dirty=False, metadata=None,
    )

    assert parse_args(["from", "any", "--metadata"]) == Namespace(
        command="from", vcs="any", pattern=None, dirty=False, metadata=True,
    )
    assert parse_args(["from", "any", "--no-metadata"]) == Namespace(
        command="from", vcs="any", pattern=None, dirty=False, metadata=False,
    )

    assert parse_args(["from", "any", "--dirty"]) == Namespace(
        command="from", vcs="any", pattern=None, dirty=True, metadata=None,
    )
