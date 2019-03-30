
import argparse
import sys
from enum import Enum
from typing import Optional

from dunamai import Version


class Vcs(Enum):
    Any = "any"
    Git = "git"
    Mercurial = "mercurial"
    Darcs = "darcs"


class Style(Enum):
    Pep440 = "pep440"
    SemVer = "semver"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate dynamic versions",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command")

    from_sp = subparsers.add_parser(
        "from",
        help="Generate version from VCS",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    from_sp.add_argument(
        "vcs", choices=[x.value for x in Vcs],
        help="Version control system to interrogate for version info",
    )
    from_sp.add_argument(
        "--metadata", action="store_true", dest="metadata", default=None,
        help="Always include metadata",
    )
    from_sp.add_argument(
        "--no-metadata", action="store_false", dest="metadata", default=None,
        help="Never include metadata",
    )
    from_sp.add_argument(
        "--dirty", action="store_true", dest="dirty",
        help="Include dirty flag if applicable",
    )
    from_sp.add_argument(
        "--pattern",
        help=(
            "Regular expression matched against the version source;"
            " see Version.from_*() docs for more info"
        ),
    )
    from_sp.add_argument(
        "--format",
        help=(
            "Custom output format. Available substitutions:"
            " {base}, {epoch}, {pre_type}, {pre_number}, {post}, {dev}, {commit}, {dirty}"
        )
    )
    from_sp.add_argument(
        "--style", choices=[x.value for x in Style],
        help=(
            "Preconfigured output format."
            " Will default to PEP 440 if not set and no custom format given."
            " If you specify both a style and a custom format, then the format"
            " will be validated against the style's rules"
        )
    )

    return parser.parse_args(argv)


def from_vcs(
        vcs: Vcs,
        pattern: Optional[str],
        with_metadata: Optional[bool],
        with_dirty: bool,
        format: Optional[str],
        style: Optional[str],
    ) -> None:
    callbacks = {
        Vcs.Any: Version.from_any_vcs,
        Vcs.Git: Version.from_git,
        Vcs.Mercurial: Version.from_mercurial,
        Vcs.Darcs: Version.from_darcs,
    }

    arguments = []
    if pattern:
        arguments.append(pattern)

    version = callbacks[vcs](*arguments)
    print(version.serialize(with_metadata, with_dirty, format, style))


def main() -> None:
    args = parse_args()
    try:
        if args.command == "from":
            from_vcs(Vcs(args.vcs), args.pattern, args.metadata, args.dirty, args.format, args.style)
    except Exception as e:
        print(e)
        sys.exit(1)
