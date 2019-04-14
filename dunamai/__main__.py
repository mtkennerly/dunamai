import argparse
import sys
from enum import Enum
from typing import Mapping, Optional

from dunamai import Version, Style, _VERSION_PATTERN


class Vcs(Enum):
    Any = "any"
    Git = "git"
    Mercurial = "mercurial"
    Darcs = "darcs"
    Subversion = "subversion"


common_sub_args = [
    {
        "triggers": ["--metadata"],
        "action": "store_true",
        "dest": "metadata",
        "default": None,
        "help": "Always include metadata",
    },
    {
        "triggers": ["--no-metadata"],
        "action": "store_false",
        "dest": "metadata",
        "default": None,
        "help": "Never include metadata",
    },
    {
        "triggers": ["--dirty"],
        "action": "store_true",
        "dest": "dirty",
        "help": "Include dirty flag if applicable",
    },
    {
        "triggers": ["--pattern"],
        "default": _VERSION_PATTERN,
        "help": (
            "Regular expression matched against the version source."
            " This should contain one capture group named `base` corresponding to"
            " the release segment of the source, and optionally another two groups"
            " named `pre_type` and `pre_number` corresponding to the type (a, b, rc)"
            " and number of prerelease."
        ),
    },
    {
        "triggers": ["--format"],
        "help": (
            "Custom output format. Available substitutions:"
            " {base}, {epoch}, {pre_type}, {pre_number},"
            " {post}, {dev}, {commit}, {dirty}"
        ),
    },
    {
        "triggers": ["--style"],
        "choices": [x.value for x in Style],
        "help": (
            "Preconfigured output format."
            " Will default to PEP 440 if not set and no custom format given."
            " If you specify both a style and a custom format, then the format"
            " will be validated against the style's rules"
        ),
    },
]
cli_spec = {
    "description": "Generate dynamic versions",
    "sub_dest": "command",
    "sub": {
        "from": {
            "description": "Generate version from a particular VCS",
            "sub_dest": "vcs",
            "sub": {
                Vcs.Any.value: {
                    "description": "Generate version from any detected VCS",
                    "args": common_sub_args,
                },
                Vcs.Git.value: {
                    "description": "Generate version from Git",
                    "args": common_sub_args,
                },
                Vcs.Mercurial.value: {
                    "description": "Generate version from Mercurial",
                    "args": common_sub_args,
                },
                Vcs.Darcs.value: {
                    "description": "Generate version from Darcs",
                    "args": common_sub_args,
                },
                Vcs.Subversion.value: {
                    "description": "Generate version from Subversion",
                    "args": [
                        *common_sub_args,
                        {
                            "triggers": ["--tag-dir"],
                            "default": "tags",
                            "help": "Location of tags relative to the root",
                        },
                    ],
                },
            },
        }
    },
}


def build_parser(spec: Mapping, parser: argparse.ArgumentParser = None) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser(
            description=spec["description"], formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    if "args" in spec:
        for arg in spec["args"]:
            triggers = arg["triggers"]
            parser.add_argument(*triggers, **{k: v for k, v in arg.items() if k != "triggers"})
    if "sub" in spec:
        subparsers = parser.add_subparsers(dest=spec["sub_dest"])
        subparsers.required = True
        for name, sub_spec in spec["sub"].items():
            subparser = subparsers.add_parser(
                name,
                description=sub_spec.get("description"),
                formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            )
            build_parser(sub_spec, subparser)

    return parser


def parse_args(argv=None) -> argparse.Namespace:
    return build_parser(cli_spec).parse_args(argv)


def from_vcs(
    vcs: Vcs,
    pattern: Optional[str],
    metadata: Optional[bool],
    dirty: bool,
    format: Optional[str],
    style: Optional[Style],
    tag_dir: Optional[str],
) -> None:
    kwargs = {}
    if pattern:
        kwargs["pattern"] = pattern
    if tag_dir is not None:
        kwargs["tag_dir"] = tag_dir

    if vcs == Vcs.Any:
        version = Version.from_any_vcs(**kwargs)
    elif vcs == Vcs.Git:
        version = Version.from_git(**kwargs)
    elif vcs == Vcs.Mercurial:
        version = Version.from_mercurial(**kwargs)
    elif vcs == Vcs.Darcs:
        version = Version.from_darcs(**kwargs)
    elif vcs == Vcs.Subversion:
        version = Version.from_subversion(**kwargs)

    print(version.serialize(metadata, dirty, format, style))


def main() -> None:
    args = parse_args()
    try:
        if args.command == "from":
            tag_dir = getattr(args, "tag_dir", None)
            from_vcs(
                Vcs(args.vcs),
                args.pattern,
                args.metadata,
                args.dirty,
                args.format,
                Style(args.style) if args.style else None,
                tag_dir,
            )
    except Exception as e:
        print(e)
        sys.exit(1)
