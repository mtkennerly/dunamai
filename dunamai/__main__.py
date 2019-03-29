
import argparse
from enum import Enum
from typing import Optional

from dunamai import Version


class Vcs(Enum):
    Any = "any"
    Git = "git"
    Mercurial = "mercurial"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate dynamic versions",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command")

    from_sp = subparsers.add_parser("from", help="Generate version from VCS")
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

    return parser.parse_args(argv)


def from_vcs(
        vcs: Vcs,
        pattern: Optional[str],
        with_metadata: Optional[bool],
        with_dirty: bool,
        format: Optional[str],
    ) -> None:
    callbacks = {
        Vcs.Any: Version.from_any_vcs,
        Vcs.Git: Version.from_git,
        Vcs.Mercurial: Version.from_mercurial,
    }

    arguments = []
    if pattern:
        arguments.append(pattern)

    version = callbacks[vcs](*arguments)
    print(version.serialize(with_metadata, with_dirty, format))


def main() -> None:
    args = parse_args()
    if args.command == "from":
        from_vcs(Vcs(args.vcs), args.pattern, args.metadata, args.dirty, args.format)
