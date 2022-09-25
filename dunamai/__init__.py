__all__ = [
    "bump_version",
    "check_version",
    "get_version",
    "serialize_pep440",
    "serialize_pvp",
    "serialize_semver",
    "Style",
    "Vcs",
    "Version",
]

import copy
import datetime as dt
import inspect
import json
import re
import shlex
import shutil
import subprocess
from collections import OrderedDict
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import (
    Any,
    Callable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)
from xml.etree import ElementTree

VERSION_SOURCE_PATTERN = r"""
    (?x)                                                        (?# ignore whitespace)
    ^v((?P<epoch>\d+)!)?(?P<base>\d+(\.\d+)*)                   (?# v1.2.3 or v1!2000.1.2)
    ([-._]?((?P<stage>[a-zA-Z]+)[-._]?(?P<revision>\d+)?))?     (?# b0)
    (\+(?P<tagged_metadata>.+))?$                               (?# +linux)
""".strip()

# Preserve old/private name for now in case it exists in the wild
_VERSION_PATTERN = VERSION_SOURCE_PATTERN

_VALID_PEP440 = r"""
    (?x)
    ^(\d+!)?
    \d+(\.\d+)*
    ((a|b|rc)\d+)?
    (\.post\d+)?
    (\.dev\d+)?
    (\+([a-zA-Z0-9]|[a-zA-Z0-9]{2}|[a-zA-Z0-9][a-zA-Z0-9.]+[a-zA-Z0-9]))?$
""".strip()
_VALID_SEMVER = r"""
    (?x)
    ^\d+\.\d+\.\d+
    (\-[a-zA-Z0-9\-]+(\.[a-zA-Z0-9\-]+)*)?
    (\+[a-zA-Z0-9\-]+(\.[a-zA-Z0-9\-]+)*)?$
""".strip()
_VALID_PVP = r"^\d+(\.\d+)*(-[a-zA-Z0-9]+)*$"

_T = TypeVar("_T")


class Style(Enum):
    Pep440 = "pep440"
    SemVer = "semver"
    Pvp = "pvp"


class Vcs(Enum):
    Any = "any"
    Git = "git"
    Mercurial = "mercurial"
    Darcs = "darcs"
    Subversion = "subversion"
    Bazaar = "bazaar"
    Fossil = "fossil"
    Pijul = "pijul"


class Pattern(Enum):
    Default = "default"
    DefaultUnprefixed = "default-unprefixed"

    def regex(self) -> str:
        """
        Get the regular expression for this preset pattern.
        """
        variants = {
            Pattern.Default: VERSION_SOURCE_PATTERN,
            Pattern.DefaultUnprefixed: VERSION_SOURCE_PATTERN.replace("^v", "^v?", 1),
        }
        return variants[self]

    @staticmethod
    def parse(pattern: Union[str, "Pattern"]) -> str:
        """
        Parse a pattern string into a regular expression.

        If the pattern contains the capture group `?P<base>`, then it is
        returned as-is. Otherwise, it is interpreted as a variant of the
        `Pattern` enum.
        """
        if isinstance(pattern, str) and "?P<base>" in pattern:
            return pattern

        try:
            pattern = Pattern(pattern)
        except ValueError:
            raise ValueError(
                _pattern_error(
                    (
                        "The pattern does not contain the capture group '?P<base>'"
                        " and is not a known preset like '{}'".format(Pattern.Default.value)
                    ),
                    pattern,
                )
            )
        return pattern.regex()


def _pattern_error(
    primary: str, pattern: Union[str, Pattern], tags: Optional[Sequence[str]] = None
) -> str:
    parts = [primary, "Pattern:\n{}".format(pattern)]

    if tags is not None:
        parts.append("Tags:\n{}".format(tags))

    return "\n\n".join(parts)


def _run_cmd(
    command: str,
    codes: Sequence[int] = (0,),
    where: Optional[Path] = None,
    shell: bool = False,
    env: Optional[dict] = None,
) -> Tuple[int, str]:
    result = subprocess.run(
        shlex.split(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(where) if where is not None else None,
        shell=shell,
        env=env,
    )
    output = result.stdout.decode().strip()
    if codes and result.returncode not in codes:
        raise RuntimeError(
            "The command '{}' returned code {}. Output:\n{}".format(
                command, result.returncode, output
            )
        )
    return (result.returncode, output)


_MatchedVersionPattern = NamedTuple(
    "_MatchedVersionPattern",
    [
        ("matched_tag", str),
        ("base", str),
        ("stage_revision", Optional[Tuple[str, Optional[int]]]),
        ("newer_tags", Sequence[str]),
        ("tagged_metadata", Optional[str]),
        ("epoch", Optional[int]),
    ],
)


def _match_version_pattern(
    pattern: Union[str, Pattern], sources: Sequence[str], latest_source: bool
) -> _MatchedVersionPattern:
    """
    :return: Tuple of:
        * matched tag
        * base segment
        * tuple of:
          * stage
          * revision
        * any newer unmatched tags
        * tagged_metadata matched section
    """
    pattern_match = None
    base = None
    stage_revision = None
    newer_unmatched_tags = []
    tagged_metadata = None
    epoch = None  # type: Optional[Union[str, int]]

    pattern = Pattern.parse(pattern)

    for source in sources[:1] if latest_source else sources:
        try:
            pattern_match = re.search(pattern, source)
        except re.error as e:
            raise re.error(
                _pattern_error(
                    "The pattern is an invalid regular expression: {}".format(
                        e.msg  # type: ignore
                    ),
                    pattern,
                ),
                e.pattern,  # type: ignore
                e.pos,  # type: ignore
            )
        if pattern_match is None:
            newer_unmatched_tags.append(source)
            continue
        try:
            base = pattern_match.group("base")
            if base is not None:
                break
        except IndexError:
            raise ValueError(
                _pattern_error("The pattern did not include required capture group 'base'", pattern)
            )
    if pattern_match is None or base is None:
        if latest_source:
            raise ValueError(
                _pattern_error(
                    "The pattern did not match the latest tag '{}'".format(sources[0]),
                    pattern,
                    sources,
                )
            )
        else:
            raise ValueError(_pattern_error("The pattern did not match any tags", pattern, sources))

    stage = pattern_match.groupdict().get("stage")
    revision = pattern_match.groupdict().get("revision")
    tagged_metadata = pattern_match.groupdict().get("tagged_metadata")
    epoch = pattern_match.groupdict().get("epoch")
    if stage is not None:
        try:
            stage_revision = (stage, None if revision is None else int(revision))
        except ValueError:
            raise ValueError("Revision '{}' is not a valid number".format(revision))
    if epoch is not None:
        try:
            epoch = int(epoch)
        except ValueError:
            raise ValueError("Epoch '{}' is not a valid number".format(epoch))

    return _MatchedVersionPattern(
        source, base, stage_revision, newer_unmatched_tags, tagged_metadata, epoch
    )


def _blank(value: Optional[_T], default: _T) -> _T:
    return value if value is not None else default


def _escape_branch(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", value)


def _equal_if_set(x: _T, y: Optional[_T], unset: Sequence[Any] = (None,)) -> bool:
    if y in unset:
        return True
    return x == y


def _detect_vcs(expected_vcs: Optional[Vcs] = None) -> Vcs:
    checks = OrderedDict(
        [
            (Vcs.Git, "git status"),
            (Vcs.Mercurial, "hg status"),
            (Vcs.Darcs, "darcs log"),
            (Vcs.Subversion, "svn log"),
            (Vcs.Bazaar, "bzr status"),
            (Vcs.Fossil, "fossil status"),
            (Vcs.Pijul, "pijul log"),
        ]
    )

    if expected_vcs:
        command = checks[expected_vcs]
        program = command.split()[0]
        if not shutil.which(program):
            raise RuntimeError("Unable to find '{}' program".format(program))
        code, _ = _run_cmd(command, codes=[])
        if code != 0:
            raise RuntimeError(
                "This does not appear to be a {} project".format(expected_vcs.value.title())
            )
        return expected_vcs
    else:
        for vcs, command in checks.items():
            if shutil.which(command.split()[0]):
                code, _ = _run_cmd(command, codes=[])
                if code == 0:
                    return vcs
        raise RuntimeError("Unable to detect version control system.")


class _GitRefInfo:
    def __init__(
        self, ref: str, commit: str, creatordate: str, committerdate: str, taggerdate: str
    ):
        self.fullref = ref
        self.commit = commit
        self.creatordate = self.normalize_git_dt(creatordate)
        self.committerdate = self.normalize_git_dt(committerdate)
        self.taggerdate = self.normalize_git_dt(taggerdate)
        self.tag_topo_lookup = {}  # type: Mapping[str, int]

    def with_tag_topo_lookup(self, lookup: Mapping[str, int]) -> "_GitRefInfo":
        self.tag_topo_lookup = lookup
        return self

    @staticmethod
    def normalize_git_dt(timestamp: str) -> Optional[dt.datetime]:
        if timestamp == "":
            return None
        else:
            return _parse_git_timestamp_iso_strict(timestamp)

    def __repr__(self):
        return (
            "_GitRefInfo(ref={!r}, commit={!r}, creatordate={!r},"
            " committerdate={!r}, taggerdate={!r})"
        ).format(
            self.fullref, self.commit_offset, self.creatordate, self.committerdate, self.taggerdate
        )

    def best_date(self) -> Optional[dt.datetime]:
        if self.taggerdate is not None:
            return self.taggerdate
        elif self.committerdate is not None:
            return self.committerdate
        else:
            return self.creatordate

    @property
    def commit_offset(self) -> int:
        try:
            return self.tag_topo_lookup[self.fullref]
        except KeyError:
            raise RuntimeError(
                "Unable to determine commit offset for ref {} in data: {}".format(
                    self.fullref, self.tag_topo_lookup
                )
            )

    @property
    def sort_key(self) -> Tuple[int, Optional[dt.datetime]]:
        return (-self.commit_offset, self.best_date())

    @property
    def ref(self) -> str:
        return self.fullref.replace("refs/tags/", "")

    @staticmethod
    def normalize_tag_ref(ref: str) -> str:
        if ref.startswith("refs/tags/"):
            return ref
        else:
            return "refs/tags/{}".format(ref)

    @staticmethod
    def from_git_tag_topo_order(tag_branch: str) -> Mapping[str, int]:
        code, logmsg = _run_cmd(
            "git log --simplify-by-decoration --topo-order --decorate=full"
            ' {} "--format=%H%d"'.format(tag_branch)
        )
        tag_lookup = {}

        # Simulate "--decorate-refs=refs/tags/*" for older Git versions:
        filtered_lines = [
            x for x in logmsg.strip().splitlines(keepends=False) if " (" not in x or "tag: " in x
        ]

        for tag_offset, line in enumerate(filtered_lines):
            # lines have the pattern
            # <gitsha1>  (tag: refs/tags/v1.2.0b1, tag: refs/tags/v1.2.0)
            commit, _, tags = line.partition("(")
            commit = commit.strip()
            if tags:
                # remove trailing ')'
                tags = tags[:-1]
                taglist = [
                    tag.strip() for tag in tags.split(", ") if tag.strip().startswith("tag: ")
                ]
                taglist = [tag.split()[-1] for tag in taglist]
                taglist = [_GitRefInfo.normalize_tag_ref(tag) for tag in taglist]
                for tag in taglist:
                    tag_lookup[tag] = tag_offset
        return tag_lookup


@total_ordering
class Version:
    def __init__(
        self,
        base: str,
        *,
        stage: Optional[Tuple[str, Optional[int]]] = None,
        distance: int = 0,
        commit: Optional[str] = None,
        dirty: Optional[bool] = None,
        tagged_metadata: Optional[str] = None,
        epoch: Optional[int] = None,
        branch: Optional[str] = None,
        timestamp: Optional[dt.datetime] = None
    ) -> None:
        """
        :param base: Release segment, such as 0.1.0.
        :param stage: Pair of release stage (e.g., "a", "alpha", "b", "rc")
            and an optional revision number.
        :param distance: Number of commits since the last tag.
        :param commit: Commit hash/identifier.
        :param dirty: True if the working directory does not match the commit.
        :param epoch: Optional PEP 440 epoch.
        :param branch: Name of the current branch.
        :param timestamp: Timestamp of the current commit.
        """
        #: Release segment.
        self.base = base
        #: Alphabetical part of prerelease segment.
        self.stage = None
        #: Numerical part of prerelease segment.
        self.revision = None
        if stage is not None:
            self.stage, self.revision = stage
        #: Number of commits since the last tag.
        self.distance = distance
        #: Commit ID.
        self.commit = commit
        #: Whether there are uncommitted changes.
        self.dirty = dirty
        #: Any metadata segment from the tag itself.
        self.tagged_metadata = tagged_metadata
        #: Optional PEP 440 epoch.
        self.epoch = epoch
        #: Name of the current branch.
        self.branch = branch
        #: Timestamp of the current commit.
        try:
            self.timestamp = timestamp.astimezone(dt.timezone.utc) if timestamp else None
        except ValueError:
            # Will fail for naive timestamps before Python 3.6.
            self.timestamp = timestamp

        self._matched_tag = None  # type: Optional[str]
        self._newer_unmatched_tags = None  # type: Optional[Sequence[str]]

    def __str__(self) -> str:
        return self.serialize()

    def __repr__(self) -> str:
        return (
            "Version(base={!r}, stage={!r}, revision={!r}, distance={!r}, commit={!r},"
            " dirty={!r}, tagged_metadata={!r}, epoch={!r}, branch={!r}, timestamp={!r})"
        ).format(
            self.base,
            self.stage,
            self.revision,
            self.distance,
            self.commit,
            self.dirty,
            self.tagged_metadata,
            self.epoch,
            self.branch,
            self.timestamp,
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            raise TypeError(
                "Cannot compare Version with type {}".format(other.__class__.__qualname__)
            )
        return (
            self.base == other.base
            and self.stage == other.stage
            and self.revision == other.revision
            and self.distance == other.distance
            and self.commit == other.commit
            and self.dirty == other.dirty
            and self.tagged_metadata == other.tagged_metadata
            and self.epoch == other.epoch
            and self.branch == other.branch
            and self.timestamp == other.timestamp
        )

    def _matches_partial(self, other: "Version") -> bool:
        """
        Compare this version to another version, but ignore None values in the other version.
        Distance is also ignored when `other.distance == 0`.

        :param other: The version to compare to.
        :return: True if this version equals the other version.
        """
        return (
            _equal_if_set(self.base, other.base)
            and _equal_if_set(self.stage, other.stage)
            and _equal_if_set(self.revision, other.revision)
            and _equal_if_set(self.distance, other.distance, unset=[None, 0])
            and _equal_if_set(self.commit, other.commit)
            and _equal_if_set(self.dirty, other.dirty)
            and _equal_if_set(self.tagged_metadata, other.tagged_metadata)
            and _equal_if_set(self.epoch, other.epoch)
            and _equal_if_set(self.branch, other.branch)
            and _equal_if_set(self.timestamp, other.timestamp)
        )

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            raise TypeError(
                "Cannot compare Version with type {}".format(other.__class__.__qualname__)
            )

        import packaging.version as pv

        return (
            pv.Version(self.base) < pv.Version(other.base)
            and _blank(self.stage, "") < _blank(other.stage, "")
            and _blank(self.revision, 0) < _blank(other.revision, 0)
            and _blank(self.distance, 0) < _blank(other.distance, 0)
            and _blank(self.commit, "") < _blank(other.commit, "")
            and bool(self.dirty) < bool(other.dirty)
            and _blank(self.tagged_metadata, "") < _blank(other.tagged_metadata, "")
            and _blank(self.epoch, 0) < _blank(other.epoch, 0)
            and _blank(self.branch, "") < _blank(other.branch, "")
            and _blank(self.timestamp, dt.datetime(0, 0, 0, 0, 0, 0))
            < _blank(other.timestamp, dt.datetime(0, 0, 0, 0, 0, 0))
        )

    def serialize(
        self,
        metadata: Optional[bool] = None,
        dirty: bool = False,
        format: Optional[Union[str, Callable[["Version"], str]]] = None,
        style: Optional[Style] = None,
        bump: bool = False,
        tagged_metadata: bool = False,
    ) -> str:
        """
        Create a string from the version info.

        :param metadata: Metadata (commit ID, dirty flag) is normally included
            in the metadata/local version part only if the distance is nonzero.
            Set this to True to always include metadata even with no distance,
            or set it to False to always exclude it.
            This is ignored when `format` is used.
        :param dirty: Set this to True to include a dirty flag in the
            metadata if applicable. Inert when metadata=False.
            This is ignored when `format` is used.
        :param format: Custom output format. It is either a formatted string or a
            callback. In the string you can use substitutions, such as "v{base}"
            to get "v0.1.0". Available substitutions:

            * {base}
            * {stage}
            * {revision}
            * {distance}
            * {commit}
            * {dirty} which expands to either "dirty" or "clean"
            * {tagged_metadata}
            * {epoch}
            * {branch}
            * {branch_escaped} which omits any non-letter/number characters
            * {timestamp} which expands to YYYYmmddHHMMSS as UTC
        :param style: Built-in output formats. Will default to PEP 440 if not
            set and no custom format given. If you specify both a style and a
            custom format, then the format will be validated against the
            style's rules.
        :param bump: If true, increment the last part of the `base` by 1,
            unless `stage` is set, in which case either increment `revision`
            by 1 or set it to a default of 2 if there was no revision.
            Does nothing when on a commit with a version tag.
        :param tagged_metadata: If true, insert the `tagged_metadata` in the
            version as the first part of the metadata segment.
            This is ignored when `format` is used.
        """
        base = self.base
        revision = self.revision
        if bump and self.distance > 0:
            bumped = self.bump()
            base = bumped.base
            revision = bumped.revision

        if format is not None:
            if callable(format):
                new_version = copy.deepcopy(self)
                new_version.base = base
                new_version.revision = revision
                out = format(new_version)
            else:
                try:
                    out = format.format(
                        base=base,
                        stage=_blank(self.stage, ""),
                        revision=_blank(revision, ""),
                        distance=_blank(self.distance, ""),
                        commit=_blank(self.commit, ""),
                        tagged_metadata=_blank(self.tagged_metadata, ""),
                        dirty="dirty" if self.dirty else "clean",
                        epoch=_blank(self.epoch, ""),
                        branch=_blank(self.branch, ""),
                        branch_escaped=_escape_branch(_blank(self.branch, "")),
                        timestamp=self.timestamp.strftime("%Y%m%d%H%M%S") if self.timestamp else "",
                    )
                except KeyError as e:
                    raise KeyError("Format contains invalid placeholder: {}".format(e))
                except ValueError as e:
                    raise ValueError("Format is invalid: {}".format(e))
            if style is not None:
                check_version(out, style)
            return out

        if style is None:
            style = Style.Pep440
        out = ""

        meta_parts = []
        if metadata is not False:
            if tagged_metadata and self.tagged_metadata:
                meta_parts.append(self.tagged_metadata)
            if (metadata or self.distance > 0) and self.commit is not None:
                meta_parts.append(self.commit)
            if dirty and self.dirty:
                meta_parts.append("dirty")

        pre_parts = []
        if self.stage is not None:
            pre_parts.append(self.stage)
            if revision is not None:
                pre_parts.append(str(revision))
        if self.distance > 0:
            pre_parts.append("pre" if bump else "post")
            pre_parts.append(str(self.distance))

        if style == Style.Pep440:
            stage = self.stage
            post = None
            dev = None
            if stage == "post":
                stage = None
                post = revision
            elif stage == "dev":
                stage = None
                dev = revision
            if self.distance > 0:
                if bump:
                    if dev is None:
                        dev = self.distance
                    else:
                        dev += self.distance
                else:
                    if post is None and dev is None:
                        post = self.distance
                        dev = 0
                    elif dev is None:
                        dev = self.distance
                    else:
                        dev += self.distance

            out = serialize_pep440(
                base,
                stage=stage,
                revision=revision,
                post=post,
                dev=dev,
                metadata=meta_parts,
                epoch=self.epoch,
            )
        elif style == Style.SemVer:
            out = serialize_semver(base, pre=pre_parts, metadata=meta_parts)
        elif style == Style.Pvp:
            out = serialize_pvp(base, metadata=[*pre_parts, *meta_parts])

        check_version(out, style)
        return out

    @classmethod
    def parse(cls, version: str, pattern: Union[str, Pattern] = Pattern.Default) -> "Version":
        """
        Attempt to parse a string into a Version instance.

        This uses inexact heuristics, so its output may vary slightly between
        releases. Consider this a "best effort" conversion.

        :param version: Full version, such as 0.3.0a3+d7.gb6a9020.dirty.
        :param pattern: Regular expression matched against the version.
            Refer to `from_any_vcs` for more info.
        """
        try:
            normalized = version
            if not version.startswith("v") and pattern in [VERSION_SOURCE_PATTERN, Pattern.Default]:
                normalized = "v{}".format(version)
            matched_pattern = _match_version_pattern(pattern, [normalized], True)
        except ValueError:
            return cls(version)

        base = matched_pattern.base
        stage = matched_pattern.stage_revision
        distance = None
        commit = None
        dirty = None
        tagged_metadata = matched_pattern.tagged_metadata
        epoch = matched_pattern.epoch

        if tagged_metadata:
            pop = []  # type: list
            parts = tagged_metadata.split(".")

            for i, value in enumerate(parts):
                if dirty is None:
                    if value == "dirty":
                        dirty = True
                        pop.append(i)
                        continue
                    elif value == "clean":
                        dirty = False
                        pop.append(i)
                        continue
                if distance is None:
                    match = re.match(r"d?(\d+)", value)
                    if match:
                        distance = int(match.group(1))
                        pop.append(i)
                        continue
                if commit is None:
                    match = re.match(r"g?([\da-z]+)", value)
                    if match:
                        commit = match.group(1)
                        pop.append(i)
                        continue

            for i in reversed(sorted(pop)):
                parts.pop(i)

            tagged_metadata = ".".join(parts)

        if distance is None:
            distance = 0
        if tagged_metadata is not None and tagged_metadata.strip() == "":
            tagged_metadata = None

        return cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
            epoch=epoch,
        )

    def bump(self, index: int = -1) -> "Version":
        """
        Increment the version.

        The base is bumped unless there is a stage defined, in which case,
        the revision is bumped instead.

        :param index: Numerical position to increment in the base. Default: -1.
            This follows Python indexing rules, so positive numbers start from
            the left side and count up from 0, while negative numbers start from
            the right side and count down from -1.
            Only has an effect when the base is bumped.
        :return: Bumped version.
        """
        bumped = copy.deepcopy(self)
        if bumped.stage is None:
            bumped.base = bump_version(bumped.base, index)
        else:
            if bumped.revision is None:
                bumped.revision = 2
            else:
                bumped.revision = bumped.revision + 1
        return bumped

    @classmethod
    def from_git(
        cls,
        pattern: Union[str, Pattern] = Pattern.Default,
        latest_tag: bool = False,
        tag_branch: Optional[str] = None,
        full_commit: bool = False,
    ) -> "Version":
        r"""
        Determine a version based on Git tags.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        :param tag_branch: Branch on which to find tags, if different than the
            current branch.
        :param full_commit: Get the full commit hash instead of the short form.
        """
        _detect_vcs(Vcs.Git)
        if tag_branch is None:
            tag_branch = "HEAD"

        code, msg = _run_cmd("git symbolic-ref --short HEAD", codes=[0, 128])
        if code == 128:
            branch = None
        else:
            branch = msg

        code, msg = _run_cmd(
            'git log -n 1 --format="format:{}"'.format("%H" if full_commit else "%h"),
            codes=[0, 128],
        )
        if code == 128:
            return cls("0.0.0", distance=0, dirty=True, branch=branch)
        commit = msg

        code, msg = _run_cmd('git log -n 1 --pretty=format:"%cI"')
        timestamp = _parse_git_timestamp_iso_strict(msg)

        code, msg = _run_cmd("git describe --always --dirty")
        dirty = msg.endswith("-dirty")

        if not dirty:
            code, msg = _run_cmd("git status --porcelain")
            if msg.strip() != "":
                dirty = True

        code, msg = _run_cmd(
            'git for-each-ref "refs/tags/**" --merged {}'.format(tag_branch)
            + ' --format "%(refname)'
            "@{%(objectname)"
            "@{%(creatordate:iso-strict)"
            "@{%(*committerdate:iso-strict)"
            "@{%(taggerdate:iso-strict)"
            '"'
        )
        if not msg:
            try:
                code, msg = _run_cmd("git rev-list --count HEAD")
                distance = int(msg)
            except Exception:
                distance = 0
            return cls(
                "0.0.0",
                distance=distance,
                commit=commit,
                dirty=dirty,
                branch=branch,
                timestamp=timestamp,
            )

        detailed_tags = []  # type: List[_GitRefInfo]
        tag_topo_lookup = _GitRefInfo.from_git_tag_topo_order(tag_branch)

        for line in msg.strip().splitlines():
            parts = line.split("@{")
            detailed_tags.append(_GitRefInfo(*parts).with_tag_topo_lookup(tag_topo_lookup))

        tags = [t.ref for t in sorted(detailed_tags, key=lambda x: x.sort_key, reverse=True)]
        tag, base, stage, unmatched, tagged_metadata, epoch = _match_version_pattern(
            pattern, tags, latest_tag
        )

        code, msg = _run_cmd("git rev-list --count refs/tags/{}..HEAD".format(tag))
        distance = int(msg)

        version = cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
            epoch=epoch,
            branch=branch,
            timestamp=timestamp,
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_mercurial(
        cls,
        pattern: Union[str, Pattern] = Pattern.Default,
        latest_tag: bool = False,
        full_commit: bool = False,
    ) -> "Version":
        r"""
        Determine a version based on Mercurial tags.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        :param full_commit: Get the full commit hash instead of the short form.
        """
        _detect_vcs(Vcs.Mercurial)

        code, msg = _run_cmd("hg summary")
        dirty = "commit: (clean)" not in msg.splitlines()

        code, msg = _run_cmd("hg branch")
        branch = msg

        code, msg = _run_cmd(
            'hg id --template "{}"'.format("{id}" if full_commit else "{id|short}")
        )
        commit = msg if set(msg) != {"0"} else None

        code, msg = _run_cmd('hg log --limit 1 --template "{date|rfc3339date}"')
        timestamp = _parse_git_timestamp_iso_strict(msg) if msg != "" else None

        code, msg = _run_cmd(
            'hg log -r "sort(tag(){}, -rev)" --template "{{join(tags, \':\')}}\\n"'.format(
                " and ancestors({})".format(commit) if commit is not None else ""
            )
        )
        if not msg:
            try:
                code, msg = _run_cmd("hg id --num --rev tip")
                distance = int(msg) + 1
            except Exception:
                distance = 0
            return cls(
                "0.0.0",
                distance=distance,
                commit=commit,
                dirty=dirty,
                branch=branch,
                timestamp=timestamp,
            )
        tags = [tag for tags in [line.split(":") for line in msg.splitlines()] for tag in tags]
        tag, base, stage, unmatched, tagged_metadata, epoch = _match_version_pattern(
            pattern, tags, latest_tag
        )

        code, msg = _run_cmd('hg log -r "{0}::{1} - {0}" --template "."'.format(tag, commit))
        # The tag itself is in the list, so offset by 1.
        distance = max(len(msg) - 1, 0)

        version = cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
            epoch=epoch,
            branch=branch,
            timestamp=timestamp,
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_darcs(
        cls, pattern: Union[str, Pattern] = Pattern.Default, latest_tag: bool = False
    ) -> "Version":
        r"""
        Determine a version based on Darcs tags.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        """
        _detect_vcs(Vcs.Darcs)

        code, msg = _run_cmd("darcs status", codes=[0, 1])
        dirty = msg != "No changes!"

        code, msg = _run_cmd("darcs log --last 1 --xml-output")
        root = ElementTree.fromstring(msg)
        if len(root) == 0:
            commit = None
            timestamp = None
        else:
            commit = root[0].attrib["hash"]
            timestamp = dt.datetime.strptime(root[0].attrib["date"] + "+0000", "%Y%m%d%H%M%S%z")

        code, msg = _run_cmd("darcs show tags")
        if not msg:
            try:
                code, msg = _run_cmd("darcs log --count")
                distance = int(msg)
            except Exception:
                distance = 0
            return cls("0.0.0", distance=distance, commit=commit, dirty=dirty, timestamp=timestamp)
        tags = msg.splitlines()
        tag, base, stage, unmatched, tagged_metadata, epoch = _match_version_pattern(
            pattern, tags, latest_tag
        )

        code, msg = _run_cmd("darcs log --from-tag {} --count".format(tag))
        # The tag itself is in the list, so offset by 1.
        distance = int(msg) - 1

        version = cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
            epoch=epoch,
            timestamp=timestamp,
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_subversion(
        cls,
        pattern: Union[str, Pattern] = Pattern.Default,
        latest_tag: bool = False,
        tag_dir: str = "tags",
    ) -> "Version":
        r"""
        Determine a version based on Subversion tags.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        :param tag_dir: Location of tags relative to the root.
        """
        _detect_vcs(Vcs.Subversion)

        tag_dir = tag_dir.strip("/")

        code, msg = _run_cmd("svn status")
        dirty = bool(msg)

        code, msg = _run_cmd("svn info --show-item repos-root-url")
        url = msg.strip("/")

        code, msg = _run_cmd("svn info --show-item revision")
        if not msg or msg == "0":
            commit = None
        else:
            commit = msg

        timestamp = None
        if commit:
            code, msg = _run_cmd("svn info --show-item last-changed-date")
            timestamp = _parse_timestamp(msg)

        if not commit:
            return cls("0.0.0", distance=0, commit=commit, dirty=dirty, timestamp=timestamp)
        code, msg = _run_cmd('svn ls -v -r {} "{}/{}"'.format(commit, url, tag_dir))
        lines = [line.split(maxsplit=5) for line in msg.splitlines()[1:]]
        tags_to_revs = {line[-1].strip("/"): int(line[0]) for line in lines}
        if not tags_to_revs:
            try:
                distance = int(commit)
            except Exception:
                distance = 0
            return cls("0.0.0", distance=distance, commit=commit, dirty=dirty, timestamp=timestamp)
        tags_to_sources_revs = {}
        for tag, rev in tags_to_revs.items():
            code, msg = _run_cmd('svn log -v "{}/{}/{}" --stop-on-copy'.format(url, tag_dir, tag))
            for line in msg.splitlines():
                match = re.search(r"A /{}/{} \(from .+?:(\d+)\)".format(tag_dir, tag), line)
                if match:
                    source = int(match.group(1))
                    tags_to_sources_revs[tag] = (source, rev)
        tags = sorted(tags_to_sources_revs, key=lambda x: tags_to_sources_revs[x], reverse=True)
        tag, base, stage, unmatched, tagged_metadata, epoch = _match_version_pattern(
            pattern, tags, latest_tag
        )

        source, rev = tags_to_sources_revs[tag]
        # The tag itself is in the list, so offset by 1.
        distance = int(commit) - 1 - source

        version = cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
            epoch=epoch,
            timestamp=timestamp,
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_bazaar(
        cls, pattern: Union[str, Pattern] = Pattern.Default, latest_tag: bool = False
    ) -> "Version":
        r"""
        Determine a version based on Bazaar tags.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        """
        _detect_vcs(Vcs.Bazaar)

        code, msg = _run_cmd("bzr status")
        dirty = msg != ""

        code, msg = _run_cmd("bzr log --limit 1")
        commit = None
        branch = None
        timestamp = None
        for line in msg.splitlines():
            info = line.split("revno: ", maxsplit=1)
            if len(info) == 2:
                commit = info[1]

            info = line.split("branch nick: ", maxsplit=1)
            if len(info) == 2:
                branch = info[1]

            info = line.split("timestamp: ", maxsplit=1)
            if len(info) == 2:
                timestamp = dt.datetime.strptime(info[1], "%a %Y-%m-%d %H:%M:%S %z")

        code, msg = _run_cmd("bzr tags")
        if not msg or not commit:
            try:
                distance = int(commit) if commit is not None else 0
            except Exception:
                distance = 0
            return cls(
                "0.0.0",
                distance=distance,
                commit=commit,
                dirty=dirty,
                branch=branch,
                timestamp=timestamp,
            )
        tags_to_revs = {
            line.split()[0]: int(line.split()[1])
            for line in msg.splitlines()
            if line.split()[1] != "?"
        }
        tags = [x[1] for x in sorted([(v, k) for k, v in tags_to_revs.items()], reverse=True)]
        tag, base, stage, unmatched, tagged_metadata, epoch = _match_version_pattern(
            pattern, tags, latest_tag
        )

        distance = int(commit) - tags_to_revs[tag]

        version = cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
            epoch=epoch,
            branch=branch,
            timestamp=timestamp,
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_fossil(
        cls, pattern: Union[str, Pattern] = Pattern.Default, latest_tag: bool = False
    ) -> "Version":
        r"""
        Determine a version based on Fossil tags.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag for a pattern
            match. If false, keep looking at tags until there is a match.
        """
        _detect_vcs(Vcs.Fossil)

        code, msg = _run_cmd("fossil changes --differ")
        dirty = bool(msg)

        code, msg = _run_cmd("fossil branch current")
        branch = msg

        code, msg = _run_cmd(
            "fossil sql \"SELECT value FROM vvar WHERE name = 'checkout-hash' LIMIT 1\""
        )
        commit = msg.strip("'")

        code, msg = _run_cmd(
            'fossil sql "'
            "SELECT DATETIME(mtime) FROM event JOIN blob ON event.objid=blob.rid WHERE type = 'ci'"
            " AND uuid = (SELECT value FROM vvar WHERE name = 'checkout-hash' LIMIT 1) LIMIT 1\""
        )
        timestamp = dt.datetime.strptime(msg.strip("'") + "+0000", "%Y-%m-%d %H:%M:%S%z")

        code, msg = _run_cmd("fossil sql \"SELECT count() FROM event WHERE type = 'ci'\"")
        # The repository creation itself counts as a commit.
        total_commits = int(msg) - 1
        if total_commits <= 0:
            return cls(
                "0.0.0", distance=0, commit=commit, dirty=dirty, branch=branch, timestamp=timestamp
            )

        # Based on `compute_direct_ancestors` from descendants.c in the
        # Fossil source code:
        query = """
            CREATE TEMP TABLE IF NOT EXISTS
                dunamai_ancestor(
                    rid INTEGER UNIQUE NOT NULL,
                    generation INTEGER PRIMARY KEY
                );
            DELETE FROM dunamai_ancestor;
            WITH RECURSIVE g(x, i)
                AS (
                    VALUES((SELECT value FROM vvar WHERE name = 'checkout' LIMIT 1), 1)
                    UNION ALL
                    SELECT plink.pid, g.i + 1 FROM plink, g
                    WHERE plink.cid = g.x AND plink.isprim
                )
                INSERT INTO dunamai_ancestor(rid, generation) SELECT x, i FROM g;
            SELECT tag.tagname, dunamai_ancestor.generation
                FROM tag
                JOIN tagxref ON tag.tagid = tagxref.tagid
                JOIN event ON tagxref.origid = event.objid
                JOIN dunamai_ancestor ON tagxref.origid = dunamai_ancestor.rid
                WHERE tagxref.tagtype = 1
                ORDER BY event.mtime DESC, tagxref.mtime DESC;
        """
        code, msg = _run_cmd('fossil sql "{}"'.format(" ".join(query.splitlines())))
        if not msg:
            try:
                distance = int(total_commits)
            except Exception:
                distance = 0
            return cls(
                "0.0.0",
                distance=distance,
                commit=commit,
                dirty=dirty,
                branch=branch,
                timestamp=timestamp,
            )

        tags_to_distance = [
            (line.rsplit(",", 1)[0][5:-1], int(line.rsplit(",", 1)[1]) - 1)
            for line in msg.splitlines()
        ]
        tag, base, stage, unmatched, tagged_metadata, epoch = _match_version_pattern(
            pattern, [t for t, d in tags_to_distance], latest_tag
        )
        distance = dict(tags_to_distance)[tag]

        version = cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
            epoch=epoch,
            branch=branch,
            timestamp=timestamp,
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_pijul(
        cls, pattern: Union[str, Pattern] = Pattern.Default, latest_tag: bool = False
    ) -> "Version":
        r"""
        Determine a version based on Pijul tags.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        """
        _detect_vcs(Vcs.Pijul)

        code, msg = _run_cmd("pijul diff --short")
        dirty = msg.strip() != ""

        code, msg = _run_cmd("pijul channel")
        branch = "main"
        for line in msg.splitlines():
            if line.startswith("* "):
                branch = line.split("* ", 1)[1]
                break

        code, msg = _run_cmd("pijul log --limit 1 --output-format json")
        limited_commits = json.loads(msg)
        if len(limited_commits) == 0:
            return cls("0.0.0", dirty=dirty, branch=branch)

        commit = limited_commits[0]["hash"]
        timestamp = _parse_timestamp(limited_commits[0]["timestamp"])

        code, msg = _run_cmd("pijul log --output-format json")
        channel_commits = json.loads(msg)

        code, msg = _run_cmd("pijul tag")
        if not msg:
            # The channel creation is in the list, so offset by 1.
            distance = len(channel_commits) - 1
            return cls(
                "0.0.0",
                distance=distance,
                commit=commit,
                dirty=dirty,
                branch=branch,
                timestamp=timestamp,
            )

        tag_meta = []  # type: List[dict]
        tag_state = ""
        tag_timestamp = dt.datetime.now()
        tag_message = ""
        tag_after_header = False
        for line in msg.splitlines():
            if not tag_after_header:
                if line.startswith("State "):
                    tag_state = line.split("State ", 1)[1]
                elif line.startswith("Date:"):
                    tag_timestamp = _parse_timestamp(
                        line.split("Date: ", 1)[1].replace(" UTC", "Z"), space=True
                    )
                elif line.startswith("    "):
                    tag_message += line[4:]
                    tag_after_header = True
            else:
                if line.startswith("State "):
                    tag_meta.append(
                        {
                            "state": tag_state,
                            "timestamp": tag_timestamp,
                            "message": tag_message.strip(),
                        }
                    )

                    tag_state = line.split("State ", 1)[1]
                    tag_timestamp = dt.datetime.now()
                    tag_message = ""
                    tag_after_header = False
                else:
                    tag_message += line
        if tag_after_header:
            tag_meta.append(
                {"state": tag_state, "timestamp": tag_timestamp, "message": tag_message.strip()}
            )

        tag_meta_by_msg = {}  # type: dict
        for meta in tag_meta:
            if (
                meta["message"] not in tag_meta_by_msg
                or meta["timestamp"] > tag_meta_by_msg[meta["message"]]["timestamp"]
            ):
                tag_meta_by_msg[meta["message"]] = meta

        tags = [
            t["message"]
            for t in sorted(tag_meta_by_msg.values(), key=lambda x: x["timestamp"], reverse=True)
        ]
        tag, base, stage, unmatched, tagged_metadata, epoch = _match_version_pattern(
            pattern, tags, latest_tag
        )

        tag_id = tag_meta_by_msg[tag]["state"]
        _run_cmd("pijul tag checkout {}".format(tag_id), codes=[0, 1])
        code, msg = _run_cmd("pijul log --output-format json --channel {}".format(tag_id))
        if msg.strip() == "":
            tag_commits = []  # type: list
        else:
            tag_commits = json.loads(msg)

        distance = len(channel_commits) - len(tag_commits)

        version = cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
            epoch=epoch,
            branch=branch,
            timestamp=timestamp,
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_any_vcs(
        cls,
        pattern: Union[str, Pattern] = Pattern.Default,
        latest_tag: bool = False,
        tag_dir: str = "tags",
        tag_branch: Optional[str] = None,
        full_commit: bool = False,
    ) -> "Version":
        r"""
        Determine a version based on a detected version control system.

        :param pattern: Regular expression matched against the version source.
            This must contain one capture group named `base` corresponding to
            the release segment of the source. Optionally, it may contain another
            two groups named `stage` and `revision` corresponding to a prerelease
            type (such as 'alpha' or 'rc') and number (such as in 'alpha-2' or 'rc3').
            It may also contain a group named `tagged_metadata` corresponding to extra
            metadata after the main part of the version (typically after a plus sign).
            There may also be a group named `epoch` for the PEP 440 concept.

            If the `base` group is not included, then this will be interpreted
            as the name of a variant of the `Pattern` enum. For example, passing
            `"default"` is the same as passing `Pattern.Default`.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        :param tag_dir: Location of tags relative to the root.
            This is only used for Subversion.
        :param tag_branch: Branch on which to find tags, if different than the
            current branch. This is only used for Git currently.
        :param full_commit: Get the full commit hash instead of the short form.
            This is only used for Git and Mercurial.
        """
        vcs = _detect_vcs()
        return cls._do_vcs_callback(vcs, pattern, latest_tag, tag_dir, tag_branch, full_commit)

    @classmethod
    def from_vcs(
        cls,
        vcs: Vcs,
        pattern: Union[str, Pattern] = Pattern.Default,
        latest_tag: bool = False,
        tag_dir: str = "tags",
        tag_branch: Optional[str] = None,
        full_commit: bool = False,
    ) -> "Version":
        r"""
        Determine a version based on a specific VCS setting.

        This is primarily intended for other tools that want to generically
        use some VCS setting based on user configuration, without having to
        maintain a mapping from the VCS name to the appropriate function.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        :param tag_dir: Location of tags relative to the root.
            This is only used for Subversion.
        :param tag_branch: Branch on which to find tags, if different than the
            current branch. This is only used for Git currently.
        :param full_commit: Get the full commit hash instead of the short form.
            This is only used for Git and Mercurial.
        """
        return cls._do_vcs_callback(vcs, pattern, latest_tag, tag_dir, tag_branch, full_commit)

    @classmethod
    def _do_vcs_callback(
        cls,
        vcs: Vcs,
        pattern: Union[str, Pattern],
        latest_tag: bool,
        tag_dir: str,
        tag_branch: Optional[str],
        full_commit: bool,
    ) -> "Version":
        mapping = {
            Vcs.Any: cls.from_any_vcs,
            Vcs.Git: cls.from_git,
            Vcs.Mercurial: cls.from_mercurial,
            Vcs.Darcs: cls.from_darcs,
            Vcs.Subversion: cls.from_subversion,
            Vcs.Bazaar: cls.from_bazaar,
            Vcs.Fossil: cls.from_fossil,
            Vcs.Pijul: cls.from_pijul,
        }  # type: Mapping[Vcs, Callable[..., "Version"]]
        kwargs = {"pattern": pattern, "latest_tag": latest_tag}  # type: dict
        callback = mapping[vcs]
        for kwarg, value in [
            ("tag_branch", tag_branch),
            ("full_commit", full_commit),
            ("tag_dir", tag_dir),
        ]:
            if kwarg in inspect.getfullargspec(callback).args:
                kwargs[kwarg] = value
        return callback(**kwargs)


def check_version(version: str, style: Style = Style.Pep440) -> None:
    """
    Check if a version is valid for a style.

    :param version: Version to check.
    :param style: Style against which to check.
    """
    name, pattern = {
        Style.Pep440: ("PEP 440", _VALID_PEP440),
        Style.SemVer: ("Semantic Versioning", _VALID_SEMVER),
        Style.Pvp: ("PVP", _VALID_PVP),
    }[style]
    failure_message = "Version '{}' does not conform to the {} style".format(version, name)
    if not re.search(pattern, version):
        raise ValueError(failure_message)
    if style == Style.SemVer:
        parts = re.split(r"[.-]", version.split("+", 1)[0])
        if any(re.search(r"^0[0-9]+$", x) for x in parts):
            raise ValueError(failure_message)


def get_version(
    name: str,
    first_choice: Optional[Callable[[], Optional[Version]]] = None,
    third_choice: Optional[Callable[[], Optional[Version]]] = None,
    fallback: Version = Version("0.0.0"),
    ignore: Optional[Sequence[Version]] = None,
    parser: Callable[[str], Version] = Version,
) -> Version:
    """
    Check pkg_resources info or a fallback function to determine the version.
    This is intended as a convenient default for setting your `__version__` if
    you do not want to include a generated version statically during packaging.

    :param name: Installed package name.
    :param first_choice: Callback to determine a version before checking
        to see if the named package is installed.
    :param third_choice: Callback to determine a version if the installed
        package cannot be found by name.
    :param fallback: If no other matches found, use this version.
    :param ignore: Ignore a found version if it is part of this list. When
        comparing the found version to an ignored one, fields with None in the ignored
        version are not taken into account. If the ignored version has distance=0,
        then that field is also ignored.
    :param parser: Callback to convert a string into a Version instance.
        This will be used for the second choice.
        For example, you can pass `Version.parse` here.
    """
    if ignore is None:
        ignore = []

    if first_choice:
        first_ver = first_choice()
        if first_ver and not any(first_ver._matches_partial(v) for v in ignore):
            return first_ver

    try:
        import importlib.metadata as ilm
    except ImportError:
        import importlib_metadata as ilm  # type: ignore
    try:
        ilm_version = parser(ilm.version(name))
        if not any(ilm_version._matches_partial(v) for v in ignore):
            return ilm_version
    except ilm.PackageNotFoundError:
        pass

    if third_choice:
        third_ver = third_choice()
        if third_ver and not any(third_ver._matches_partial(v) for v in ignore):
            return third_ver

    return fallback


def serialize_pep440(
    base: str,
    stage: Optional[str] = None,
    revision: Optional[int] = None,
    post: Optional[int] = None,
    dev: Optional[int] = None,
    epoch: Optional[int] = None,
    metadata: Optional[Sequence[Union[str, int]]] = None,
) -> str:
    """
    Serialize a version based on PEP 440.
    Use this instead of `Version.serialize()` if you want more control
    over how the version is mapped.

    :param base: Release segment, such as 0.1.0.
    :param stage: Pre-release stage ("a", "b", or "rc").
    :param revision: Pre-release revision (e.g., 1 as in "rc1").
        This is ignored when `stage` is None.
    :param post: Post-release number.
    :param dev: Developmental release number.
    :param epoch: Epoch number.
    :param metadata: Any local version label segments.
    :return: Serialized version.
    """
    out = []  # type: list

    if epoch is not None:
        out.extend([epoch, "!"])

    out.append(base)

    if stage is not None:
        alternative_stages = {"alpha": "a", "beta": "b", "c": "rc", "pre": "rc", "preview": "rc"}
        out.append(alternative_stages.get(stage.lower(), stage.lower()))
        if revision is None:
            # PEP 440 does not allow omitting the revision, so assume 0.
            out.append(0)
        else:
            out.append(revision)

    if post is not None:
        out.extend([".post", post])

    if dev is not None:
        out.extend([".dev", dev])

    if metadata is not None and len(metadata) > 0:
        out.extend(["+", ".".join(map(str, metadata))])

    serialized = "".join(map(str, out))
    check_version(serialized, Style.Pep440)
    return serialized


def serialize_semver(
    base: str,
    pre: Optional[Sequence[Union[str, int]]] = None,
    metadata: Optional[Sequence[Union[str, int]]] = None,
) -> str:
    """
    Serialize a version based on Semantic Versioning.
    Use this instead of `Version.serialize()` if you want more control
    over how the version is mapped.

    :param base: Version core, such as 0.1.0.
    :param pre: Pre-release identifiers.
    :param metadata: Build metadata identifiers.
    :return: Serialized version.
    """
    out = [base]

    if pre is not None and len(pre) > 0:
        out.extend(["-", ".".join(map(str, pre))])

    if metadata is not None and len(metadata) > 0:
        out.extend(["+", ".".join(map(str, metadata))])

    serialized = "".join(str(x) for x in out)
    check_version(serialized, Style.SemVer)
    return serialized


def serialize_pvp(base: str, metadata: Optional[Sequence[Union[str, int]]] = None) -> str:
    """
    Serialize a version based on the Haskell Package Versioning Policy.
    Use this instead of `Version.serialize()` if you want more control
    over how the version is mapped.

    :param base: Version core, such as 0.1.0.
    :param metadata: Version tag metadata.
    :return: Serialized version.
    """
    out = [base]

    if metadata is not None and len(metadata) > 0:
        out.extend(["-", "-".join(map(str, metadata))])

    serialized = "".join(map(str, out))
    check_version(serialized, Style.Pvp)
    return serialized


def bump_version(base: str, index: int = -1) -> str:
    """
    Increment one of the numerical positions of a version.

    :param base: Version core, such as 0.1.0.
        Do not include pre-release identifiers.
    :param index: Numerical position to increment. Default: -1.
        This follows Python indexing rules, so positive numbers start from
        the left side and count up from 0, while negative numbers start from
        the right side and count down from -1.
    :return: Bumped version.
    """
    bases = [int(x) for x in base.split(".")]
    bases[index] += 1

    limit = 0 if index < 0 else len(bases)
    i = index + 1
    while i < limit:
        bases[i] = 0
        i += 1

    return ".".join(str(x) for x in bases)


def _parse_git_timestamp_iso_strict(raw: str) -> dt.datetime:
    # Remove colon from timezone offset for pre-3.7 Python:
    compat = re.sub(r"(.*T.*[-+]\d+):(\d+)", r"\1\2", raw)
    return dt.datetime.strptime(compat, "%Y-%m-%dT%H:%M:%S%z")


def _parse_timestamp(raw: str, space: bool = False) -> dt.datetime:
    if space:
        format = "%Y-%m-%d %H:%M:%S.%f%z"
    else:
        format = "%Y-%m-%dT%H:%M:%S.%f%z"

    # Normalize "Z" for pre-3.7 compatibility:
    normalized = re.sub(r"Z$", "+0000", raw)
    # Truncate %f to six digits:
    normalized = re.sub(r"\.(\d{6})\d+\+0000", r".\g<1>+0000", normalized)

    return dt.datetime.strptime(normalized, format)


__version__ = get_version("dunamai").serialize()
