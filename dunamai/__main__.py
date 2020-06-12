import argparse
import sys
from typing import Mapping, Optional

from dunamai import check_version, Version, Style, Vcs, _VERSION_PATTERN


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
            " named `stage` and `revision` corresponding to a prerelease type"
            " (such as 'alpha' or 'rc') and number (such as in 'alpha-2' or 'rc3')"
        ),
    },
    {
        "triggers": ["--format"],
        "help": (
            "Custom output format. Available substitutions:"
            " {base}, {stage}, {revision}, {distance}, {commit}, {dirty}"
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
    {
        "triggers": ["--latest-tag"],
        "action": "store_true",
        "dest": "latest_tag",
        "default": False,
        "help": "Only inspect the latest tag on the latest tagged commit for a pattern match",
    },
    {
        "triggers": ["--debug"],
        "action": "store_true",
        "dest": "debug",
        "default": False,
        "help": "Display additional information on stderr for troubleshooting",
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
                    "args": [
                        *common_sub_args,
                        {
                            "triggers": ["--tag-dir"],
                            "default": "tags",
                            "help": "Location of tags relative to the root (Subversion)",
                        },
                    ],
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
                Vcs.Bazaar.value: {
                    "description": "Generate version from Bazaar",
                    "args": common_sub_args,
                },
                Vcs.Fossil.value: {
                    "description": "Generate version from Fossil",
                    "args": common_sub_args,
                },
            },
        },
        "check": {
            "description": "Check if a version is valid for a style",
            "args": [
                {
                    "triggers": [],
                    "dest": "version",
                    "help": "Version to check; may be piped in",
                    "nargs": "?",
                },
                {
                    "triggers": ["--style"],
                    "choices": [x.value for x in Style],
                    "default": Style.Pep440.value,
                    "help": "Style against which to check",
                },
            ],
        },
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
                help=sub_spec.get("description"),
                formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            )
            build_parser(sub_spec, subparser)

    return parser


def parse_args(argv=None) -> argparse.Namespace:
    return build_parser(cli_spec).parse_args(argv)


def from_stdin(value: Optional[str]) -> Optional[str]:
    if value is not None:
        return value

    if not sys.stdin.isatty():
        return sys.stdin.readline().strip()

    return None


def from_vcs(
    vcs: Vcs,
    pattern: str,
    metadata: Optional[bool],
    dirty: bool,
    format: Optional[str],
    style: Optional[Style],
    latest_tag: bool,
    tag_dir: str,
    debug: bool,
) -> None:
    version = Version.from_vcs(vcs, pattern, latest_tag, tag_dir)
    print(version.serialize(metadata, dirty, format, style))
    if debug:
        print("# Matched tag: {}".format(version._matched_tag), file=sys.stderr)
        print("# Newer unmatched tags: {}".format(version._newer_unmatched_tags), file=sys.stderr)


def main() -> None:
    args = parse_args()
    try:
        if args.command == "from":
            tag_dir = getattr(args, "tag_dir", "tags")
            from_vcs(
                Vcs(args.vcs),
                args.pattern,
                args.metadata,
                args.dirty,
                args.format,
                Style(args.style) if args.style else None,
                args.latest_tag,
                tag_dir,
                args.debug,
            )
        elif args.command == "check":
            version = from_stdin(args.version)
            if version is None:
                raise ValueError("A version must be specified")
            check_version(version, Style(args.style))
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
