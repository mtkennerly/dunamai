__all__ = ["check_version", "get_version", "Style", "Vcs", "Version"]

import sys

from packaging.version import parse

if sys.version_info < (3, 8):
    import importlib_metadata as importlib_metadata
else:
    import importlib.metadata as importlib_metadata

import datetime as dt
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

_VERSION_PATTERN = r"""
    (?x)                                                (?# ignore whitespace)
    ^v(?P<base>\d+(\.\d+)*)                             (?# v1.2.3)
    (-?((?P<stage>[a-zA-Z]+)\.?(?P<revision>\d+)?))?    (?# b0)
    (\+(?P<tagged_metadata>.+))?$                       (?# +linux)
""".strip()

# PEP 440: [N!]N(.N)*[{a|b|rc}N][.postN][.devN][+<local version label>]
_VALID_PEP440 = r"^(\d!)?\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+.+)?$"
_VALID_SEMVER = (
    r"^\d+\.\d+\.\d+(\-[a-zA-z0-9\-]+(\.[a-zA-z0-9\-]+)*)?(\+[a-zA-z0-9\-]+(\.[a-zA-z0-9\-]+)*)?$"
)
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


def _run_cmd(
    command: str,
    codes: Sequence[int] = (0,),
    where: Path = None,
    shell: bool = False,
    env: dict = None,
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


class _MatchedVersionPattern(NamedTuple):
    matched_tag: str
    base: str
    stage_revision: Optional[Tuple[str, Optional[int]]]
    newer_tags: Sequence[str]
    tagged_metadata: Optional[str]


def _match_version_pattern(
    pattern: str, sources: Sequence[str], latest_source: bool
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

    for source in sources[:1] if latest_source else sources:
        pattern_match = re.search(pattern, source)
        if pattern_match is None:
            newer_unmatched_tags.append(source)
            continue
        try:
            base = pattern_match.group("base")
            if base is not None:
                break
        except IndexError:
            raise ValueError(f"Pattern '{pattern}' did not include required capture group 'base'")
    if pattern_match is None or base is None:
        if latest_source:
            raise ValueError(
                "Pattern '{}' did not match the latest tag '{}' from {}".format(
                    pattern, sources[0], sources
                )
            )
        else:
            raise ValueError(f"Pattern '{pattern}' did not match any tags from {sources}")

    try:
        stage = pattern_match.group("stage")
        revision = pattern_match.group("revision")
        tagged_metadata = pattern_match.group("tagged_metadata")
        if stage is not None:
            stage_revision = (stage, None) if revision is None else (stage, int(revision))
    except IndexError:
        pass

    return _MatchedVersionPattern(
        source, base, stage_revision, newer_unmatched_tags, tagged_metadata
    )


def _blank(value: Optional[_T], default: _T) -> _T:
    return value if value is not None else default


def _detect_vcs(expected_vcs: Vcs = None) -> Vcs:
    checks = OrderedDict(
        [
            (Vcs.Git, "git status"),
            (Vcs.Mercurial, "hg status"),
            (Vcs.Darcs, "darcs log"),
            (Vcs.Subversion, "svn log"),
            (Vcs.Bazaar, "bzr status"),
            (Vcs.Fossil, "fossil status"),
        ]
    )

    if expected_vcs:
        command = checks[expected_vcs]
        program = command.split()[0]
        if not shutil.which(program):
            raise RuntimeError(f"Unable to find '{program}' program")
        code, _ = _run_cmd(command, codes=[])
        if code != 0:
            raise RuntimeError(f"This does not appear to be a {expected_vcs.value.title()} project")
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
            return f"refs/tags/{ref}"

    @staticmethod
    def from_git_tag_topo_order() -> Mapping[str, int]:
        code, logmsg = _run_cmd(
            'git log --simplify-by-decoration --topo-order --decorate=full HEAD "--format=%H%d"'
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
        stage: Tuple[str, Optional[int]] = None,
        distance: int = 0,
        commit: str = None,
        dirty: bool = None,
        tagged_metadata: Optional[str] = None,
    ) -> None:
        """
        :param base: Release segment, such as 0.1.0.
        :param stage: Pair of release stage (e.g., "a", "alpha", "b", "rc")
            and an optional revision number.
        :param distance: Number of commits since the last tag.
        :param commit: Commit hash/identifier.
        :param dirty: True if the working directory does not match the commit.
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

        self._matched_tag = None  # type: Optional[str]
        self._newer_unmatched_tags = None  # type: Optional[Sequence[str]]

    def __str__(self) -> str:
        return self.serialize()

    def __repr__(self) -> str:
        return (
            "Version(base={!r}, stage={!r}, revision={!r},"
            " distance={!r}, commit={!r}, dirty={!r}, tagged_metadata={!r})"
        ).format(
            self.base,
            self.stage,
            self.revision,
            self.distance,
            self.commit,
            self.dirty,
            self.tagged_metadata,
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            raise TypeError(f"Cannot compare Version with type {other.__class__.__qualname__}")
        return (
            self.base == other.base
            and self.stage == other.stage
            and self.revision == other.revision
            and self.distance == other.distance
            and self.commit == other.commit
            and self.dirty == other.dirty
        )

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            raise TypeError(f"Cannot compare Version with type {other.__class__.__qualname__}")
        return (
            parse(self.base) < parse(other.base)
            and _blank(self.stage, "") < _blank(other.stage, "")
            and _blank(self.revision, 0) < _blank(other.revision, 0)
            and _blank(self.distance, 0) < _blank(other.distance, 0)
            and _blank(self.commit, "") < _blank(other.commit, "")
            and bool(self.dirty) < bool(other.dirty)
        )

    def serialize(
        self,
        metadata: bool = None,
        dirty: bool = False,
        format: str = None,
        style: Style = None,
        bump: bool = False,
        tagged_metadata: bool = False,
    ) -> str:
        """
        Create a string from the version info.

        :param metadata: Metadata (commit ID, dirty flag) is normally included
            in the metadata/local version part only if the distance is nonzero.
            Set this to True to always include metadata even with no distance,
            or set it to False to always exclude it.
        :param dirty: Set this to True to include a dirty flag in the
            metadata if applicable. Inert when metadata=False.
        :param format: Custom output format. You can use substitutions, such as
            "v{base}" to get "v0.1.0". Available substitutions:

            * {base}
            * {stage}
            * {revision}
            * {distance}
            * {commit}
            * {dirty} which expands to either "dirty" or "clean"
            * {tagged_metadata}
        :param style: Built-in output formats. Will default to PEP 440 if not
            set and no custom format given. If you specify both a style and a
            custom format, then the format will be validated against the
            style's rules.
        :param bump: If true, increment the last part of the `base` by 1,
            unless `stage` is set, in which case either increment `revision`
            by 1 or set it to a default of 2 if there was no revision.
        :param tagged_metadata: If true, insert the `tagged_metadata` in the
            version as the first part of the metadata segment.
        """
        base = self.base
        revision = self.revision
        if bump:
            if self.stage is None:
                base = bump_version(self.base)
            else:
                if self.revision is None:
                    revision = 2
                else:
                    revision = self.revision + 1

        if format is not None:
            out = format.format(
                base=base,
                stage=_blank(self.stage, ""),
                revision=_blank(revision, ""),
                distance=_blank(self.distance, ""),
                commit=_blank(self.commit, ""),
                tagged_metadata=_blank(self.tagged_metadata, ""),
                dirty="dirty" if self.dirty else "clean",
            )
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
            if self.distance <= 0:
                out = serialize_pep440(
                    base, stage=self.stage, revision=revision, metadata=meta_parts
                )
            else:
                out = serialize_pep440(
                    base,
                    stage=self.stage,
                    revision=revision,
                    post=None if bump else self.distance,
                    dev=self.distance if bump else 0,
                    metadata=meta_parts,
                )
        elif style == Style.SemVer:
            out = serialize_semver(base, pre=pre_parts, metadata=meta_parts)
        elif style == Style.Pvp:
            out = serialize_pvp(base, metadata=[*pre_parts, *meta_parts])

        check_version(out, style)
        return out

    @classmethod
    def from_git(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
        r"""
        Determine a version based on Git tags.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        """
        _detect_vcs(Vcs.Git)

        code, msg = _run_cmd('git log -n 1 --format="format:%h"', codes=[0, 128])
        if code == 128:
            return cls("0.0.0", distance=0, dirty=True)
        commit = msg

        code, msg = _run_cmd("git describe --always --dirty")
        dirty = msg.endswith("-dirty")

        if not dirty:
            code, msg = _run_cmd("git status --porcelain")
            if msg.strip() != "":
                dirty = True

        code, msg = _run_cmd(
            'git for-each-ref "refs/tags/**" --merged HEAD'
            ' --format "%(refname)'
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
            return cls("0.0.0", distance=distance, commit=commit, dirty=dirty)

        detailed_tags = []  # type: List[_GitRefInfo]
        tag_topo_lookup = _GitRefInfo.from_git_tag_topo_order()

        for line in msg.strip().splitlines():
            parts = line.split("@{")
            detailed_tags.append(_GitRefInfo(*parts).with_tag_topo_lookup(tag_topo_lookup))

        tags = [t.ref for t in sorted(detailed_tags, key=lambda x: x.sort_key, reverse=True)]
        tag, base, stage, unmatched, tagged_metadata = _match_version_pattern(
            pattern, tags, latest_tag
        )

        code, msg = _run_cmd(f"git rev-list --count refs/tags/{tag}..HEAD")
        distance = int(msg)

        version = cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_mercurial(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
        r"""
        Determine a version based on Mercurial tags.

        :param pattern: Regular expression matched against the version source.
            Refer to `from_any_vcs` for more info.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        """
        _detect_vcs(Vcs.Mercurial)

        code, msg = _run_cmd("hg summary")
        dirty = "commit: (clean)" not in msg.splitlines()

        code, msg = _run_cmd('hg id --template "{id|short}"')
        commit = msg if set(msg) != {"0"} else None

        code, msg = _run_cmd(
            'hg log -r "sort(tag(){}, -rev)" --template "{{join(tags, \':\')}}\\n"'.format(
                f" and ancestors({commit})" if commit is not None else ""
            )
        )
        if not msg:
            try:
                code, msg = _run_cmd("hg id --num --rev tip")
                distance = int(msg) + 1
            except Exception:
                distance = 0
            return cls("0.0.0", distance=distance, commit=commit, dirty=dirty)
        tags = [tag for tags in [line.split(":") for line in msg.splitlines()] for tag in tags]
        tag, base, stage, unmatched, tagged_metadata = _match_version_pattern(
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
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_darcs(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
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

        code, msg = _run_cmd("darcs log --last 1")
        commit = msg.split()[1].strip() if msg else None

        code, msg = _run_cmd("darcs show tags")
        if not msg:
            try:
                code, msg = _run_cmd("darcs log --count")
                distance = int(msg)
            except Exception:
                distance = 0
            return cls("0.0.0", distance=distance, commit=commit, dirty=dirty)
        tags = msg.splitlines()
        tag, base, stage, unmatched, tagged_metadata = _match_version_pattern(
            pattern, tags, latest_tag
        )

        code, msg = _run_cmd(f"darcs log --from-tag {tag} --count")
        # The tag itself is in the list, so offset by 1.
        distance = int(msg) - 1

        version = cls(
            base,
            stage=stage,
            distance=distance,
            commit=commit,
            dirty=dirty,
            tagged_metadata=tagged_metadata,
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_subversion(
        cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False, tag_dir: str = "tags"
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

        if not commit:
            return cls("0.0.0", distance=0, commit=commit, dirty=dirty)
        code, msg = _run_cmd(f'svn ls -v -r {commit} "{url}/{tag_dir}"')
        lines = [line.split(maxsplit=5) for line in msg.splitlines()[1:]]
        tags_to_revs = {line[-1].strip("/"): int(line[0]) for line in lines}
        if not tags_to_revs:
            try:
                distance = int(commit)
            except Exception:
                distance = 0
            return cls("0.0.0", distance=distance, commit=commit, dirty=dirty)
        tags_to_sources_revs = {}
        for tag, rev in tags_to_revs.items():
            code, msg = _run_cmd(f'svn log -v "{url}/{tag_dir}/{tag}" --stop-on-copy')
            for line in msg.splitlines():
                match = re.search(fr"A /{tag_dir}/{tag} \(from .+?:(\d+)\)", line)
                if match:
                    source = int(match.group(1))
                    tags_to_sources_revs[tag] = (source, rev)
        tags = sorted(tags_to_sources_revs, key=lambda x: tags_to_sources_revs[x], reverse=True)
        tag, base, stage, unmatched, tagged_metadata = _match_version_pattern(
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
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_bazaar(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
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

        code, msg = _run_cmd("bzr log --limit 1 --line")
        commit = msg.split(":", 1)[0] if msg else None

        code, msg = _run_cmd("bzr tags")
        if not msg or not commit:
            try:
                distance = int(commit) if commit is not None else 0
            except Exception:
                distance = 0
            return cls("0.0.0", distance=distance, commit=commit, dirty=dirty)
        tags_to_revs = {
            line.split()[0]: int(line.split()[1])
            for line in msg.splitlines()
            if line.split()[1] != "?"
        }
        tags = [x[1] for x in sorted(((v, k) for k, v in tags_to_revs.items()), reverse=True)]
        tag, base, stage, unmatched, tagged_metadata = _match_version_pattern(
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
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_fossil(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
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

        code, msg = _run_cmd(
            "fossil sql \"SELECT value FROM vvar WHERE name = 'checkout-hash' LIMIT 1\""
        )
        commit = msg.strip("'")

        code, msg = _run_cmd("fossil sql \"SELECT count() FROM event WHERE type = 'ci'\"")
        # The repository creation itself counts as a commit.
        total_commits = int(msg) - 1
        if total_commits <= 0:
            return cls("0.0.0", distance=0, commit=commit, dirty=dirty)

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
            return cls("0.0.0", distance=distance, commit=commit, dirty=dirty)

        tags_to_distance = [
            (line.rsplit(",", 1)[0][5:-1], int(line.rsplit(",", 1)[1]) - 1)
            for line in msg.splitlines()
        ]
        tag, base, stage, unmatched, tagged_metadata = _match_version_pattern(
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
        )
        version._matched_tag = tag
        version._newer_unmatched_tags = unmatched
        return version

    @classmethod
    def from_any_vcs(
        cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False, tag_dir: str = "tags"
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
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        :param tag_dir: Location of tags relative to the root.
            This is only used for Subversion.
        """
        vcs = _detect_vcs()
        return cls._do_vcs_callback(vcs, pattern, latest_tag, tag_dir)

    @classmethod
    def from_vcs(
        cls,
        vcs: Vcs,
        pattern: str = _VERSION_PATTERN,
        latest_tag: bool = False,
        tag_dir: str = "tags",
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
        """
        return cls._do_vcs_callback(vcs, pattern, latest_tag, tag_dir)

    @classmethod
    def _do_vcs_callback(cls, vcs: Vcs, pattern: str, latest_tag: bool, tag_dir: str) -> "Version":
        mapping = {
            Vcs.Any: cls.from_any_vcs,
            Vcs.Git: cls.from_git,
            Vcs.Mercurial: cls.from_mercurial,
            Vcs.Darcs: cls.from_darcs,
            Vcs.Subversion: cls.from_subversion,
            Vcs.Bazaar: cls.from_bazaar,
            Vcs.Fossil: cls.from_fossil,
        }  # type: Mapping[Vcs, Callable[..., "Version"]]
        kwargs = {"pattern": pattern, "latest_tag": latest_tag}
        if vcs == Vcs.Subversion:
            kwargs["tag_dir"] = tag_dir
        return mapping[vcs](**kwargs)


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
    failure_message = f"Version '{version}' does not conform to the {name} style"
    if not re.search(pattern, version):
        raise ValueError(failure_message)
    if style == Style.SemVer:
        parts = re.split(r"[.-]", version.split("+", 1)[0])
        if any(re.search(r"^0[0-9]+$", x) for x in parts):
            raise ValueError(failure_message)


def get_version(
    name: str,
    first_choice: Callable[[], Optional[Version]] = None,
    third_choice: Callable[[], Optional[Version]] = None,
    fallback: Version = Version("0.0.0"),
) -> Version:
    """
    Check packaging info or a fallback function to determine the version.
    This is intended as a convenient default for setting your `__version__` if
    you do not want to include a generated version statically during packaging.

    :param name: Installed package name.
    :param first_choice: Callback to determine a version before checking
        to see if the named package is installed.
    :param third_choice: Callback to determine a version if the installed
        package cannot be found by name.
    :param fallback: If no other matches found, use this version.
    """
    if first_choice:
        first_ver = first_choice()
        if first_ver:
            return first_ver

    try:
        return Version(importlib_metadata.version(name))
    except importlib_metadata.PackageNotFoundError:
        pass

    if third_choice:
        third_ver = third_choice()
        if third_ver:
            return third_ver

    return fallback


def serialize_pep440(
    base: str,
    stage: str = None,
    revision: int = None,
    post: int = None,
    dev: int = None,
    epoch: int = None,
    metadata: Sequence[Union[str, int]] = None,
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
        out.append(stage)
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
    base: str, pre: Sequence[Union[str, int]] = None, metadata: Sequence[Union[str, int]] = None
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


def serialize_pvp(base: str, metadata: Sequence[Union[str, int]] = None) -> str:
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


__version__ = get_version("dunamai").serialize()
