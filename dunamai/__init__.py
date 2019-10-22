__all__ = ["check_version", "get_version", "Style", "Vcs", "Version"]

import os
import pkg_resources
import re
import shlex
import shutil
import subprocess
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple, TypeVar

_VERSION_PATTERN = r"v(?P<base>\d+\.\d+\.\d+)((?P<pre_type>[a-zA-Z]+)(?P<pre_number>\d+))?"
# PEP 440: [N!]N(.N)*[{a|b|rc}N][.postN][.devN][+<local version label>]
_VALID_PEP440 = r"^(\d!)?\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+.+)?$"
_VALID_SEMVER = (
    r"^\d+\.\d+\.\d+(\-[a-zA-z0-9\-]+(\.[a-zA-z0-9\-]+)*)?(\+[a-zA-z0-9\-]+(\.[a-zA-z0-9\-]+)?)?$"
)
_VALID_PVP = r"^\d+(\.\d+)*(-[a-zA-Z0-9]+)*$"

_T = TypeVar("_T")


def _run_cmd(
    command: str, codes: Sequence[int] = (0,), where: Path = None, shell: bool = False
) -> Tuple[int, str]:
    result = subprocess.run(
        shlex.split(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(where) if where is not None else None,
        shell=shell,
    )
    output = result.stdout.decode().strip()
    if codes and result.returncode not in codes:
        raise RuntimeError(
            "The command '{}' returned code {}. Output:\n{}".format(
                command, result.returncode, output
            )
        )
    return (result.returncode, output)


def _match_version_pattern(
    pattern: str, sources: Sequence[str], latest_source: bool
) -> Tuple[str, str, Optional[Tuple[str, int]]]:
    pattern_match = None
    base = None
    pre = None

    for source in sources[:1] if latest_source else sources:
        pattern_match = re.search(pattern, source)
        if pattern_match is None:
            continue
        try:
            base = pattern_match.group("base")
            if base is not None:
                break
        except IndexError:
            raise ValueError(
                "Pattern '{}' did not include required capture group 'base'".format(pattern)
            )
    if pattern_match is None or base is None:
        if latest_source:
            raise ValueError(
                "Pattern '{}' did not match the latest tag '{}' from {}".format(
                    pattern, sources[0], sources
                )
            )
        else:
            raise ValueError("Pattern '{}' did not match any tags from {}".format(pattern, sources))

    try:
        pre_type = pattern_match.group("pre_type")
        pre_number = pattern_match.group("pre_number")
        if pre_type is not None and pre_number is not None:
            pre = (pre_type, int(pre_number))
    except IndexError:
        pass

    return (source, base, pre)


def _blank(value: Optional[_T], default: _T) -> _T:
    return value if value is not None else default


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


@total_ordering
class Version:
    def __init__(
        self,
        base: str,
        *,
        epoch: int = None,
        pre: Tuple[str, int] = None,
        post: int = None,
        dev: int = None,
        commit: str = None,
        dirty: bool = None
    ) -> None:
        """
        :param base: Release segment, such as 0.1.0.
        :param epoch: Epoch number.
        :param pre: Pair of prerelease type (e.g., "a", "alpha", "b", "rc") and number.
        :param post: Postrelease number.
        :param dev: Development release number.
        :param commit: Commit hash/identifier.
        :param dirty: True if the working directory does not match the commit.
        """
        #: Release segment.
        self.base = base
        #: Epoch number.
        self.epoch = epoch
        #: Alphabetical part of prerelease segment.
        self.pre_type = None
        #: Numerical part of prerelease segment.
        self.pre_number = None
        if pre is not None:
            self.pre_type, self.pre_number = pre
        #: Postrelease number.
        self.post = post
        #: Development release number.
        self.dev = dev
        #: Commit ID.
        self.commit = commit
        #: Whether there are uncommitted changes.
        self.dirty = dirty

    def __str__(self) -> str:
        return self.serialize()

    def __repr__(self) -> str:
        return (
            "Version(base={!r}, epoch={!r}, pre_type={!r}, pre_number={!r},"
            " post={!r}, dev={!r}, commit={!r}, dirty={!r})"
        ).format(
            self.base,
            self.epoch,
            self.pre_type,
            self.pre_number,
            self.post,
            self.dev,
            self.commit,
            self.dirty,
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            raise TypeError(
                "Cannot compare Version with type {}".format(other.__class__.__qualname__)
            )
        return (
            self.epoch == other.epoch
            and self.base == other.base
            and self.pre_type == other.pre_type
            and self.pre_number == other.pre_number
            and self.post == other.post
            and self.dev == other.dev
            and self.commit == other.commit
            and self.dirty == other.dirty
        )

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            raise TypeError(
                "Cannot compare Version with type {}".format(other.__class__.__qualname__)
            )
        return (
            _blank(self.epoch, 0) < _blank(other.epoch, 0)
            and pkg_resources.parse_version(self.base) < pkg_resources.parse_version(other.base)
            and _blank(self.pre_type, "") < _blank(other.pre_type, "")
            and _blank(self.pre_number, 0) < _blank(other.pre_number, 0)
            and _blank(self.post, 0) < _blank(other.post, 0)
            and _blank(self.dev, 0) < _blank(other.dev, 0)
            and _blank(self.commit, "") < _blank(other.commit, "")
            and bool(self.dirty) < bool(other.dirty)
        )

    def serialize(
        self, metadata: bool = None, dirty: bool = False, format: str = None, style: Style = None
    ) -> str:
        """
        Create a string from the version info.

        :param metadata: Metadata (commit, dirty) is normally included in
            the local version part if post or dev are set. Set this to True to
            always include metadata, or set it to False to always exclude it.
        :param dirty: Set this to True to include a dirty flag in the
            metadata if applicable. Inert when metadata=False.
        :param format: Custom output format. You can use substitutions, such as
            "v{base}" to get "v0.1.0". However, note that PEP 440 compliance
            is not validated with custom formats. Available substitutions:

            * {base}
            * {epoch}
            * {pre_type}
            * {pre_number}
            * {post}
            * {dev}
            * {commit}
            * {dirty} which expands to either "dirty" or "clean"
        :param style: Built-in output formats. Will default to PEP 440 if not
            set and no custom format given. If you specify both a style and a
            custom format, then the format will be validated against the
            style's rules.
        """
        if format is not None:
            out = format.format(
                base=self.base,
                epoch=_blank(self.epoch, ""),
                pre_type=_blank(self.pre_type, ""),
                pre_number=_blank(self.pre_number, ""),
                post=_blank(self.post, ""),
                dev=_blank(self.dev, ""),
                commit=_blank(self.commit, ""),
                dirty="dirty" if self.dirty else "clean",
            )
            if style is not None:
                check_version(out, style)
            return out

        if style is None:
            style = Style.Pep440
        out = ""

        if style == Style.Pep440:
            if self.epoch is not None:
                out += "{}!".format(self.epoch)

            out += self.base

            if self.pre_type is not None and self.pre_number is not None:
                out += "{}{}".format(self.pre_type, self.pre_number)
            if self.post is not None:
                out += ".post{}".format(self.post)
            if self.dev is not None:
                out += ".dev{}".format(self.dev)

            if metadata is not False:
                metadata_parts = []
                if metadata or self.post is not None or self.dev is not None:
                    metadata_parts.append(self.commit)
                if dirty and self.dirty:
                    metadata_parts.append("dirty")
                metadata_segment = ".".join(x for x in metadata_parts if x is not None)
                if metadata_segment:
                    out += "+{}".format(metadata_segment)
        elif style == Style.SemVer:
            out += self.base

            pre_parts = []
            if self.epoch is not None:
                pre_parts.append(("epoch", self.epoch))
            if self.pre_type is not None and self.pre_number is not None:
                pre_parts.append((self.pre_type, self.pre_number))
            if self.post is not None:
                pre_parts.append(("post", self.post))
            if self.dev is not None:
                pre_parts.append(("dev", self.dev))
            if pre_parts:
                out += "-{}".format(".".join("{}.{}".format(k, v) for k, v in pre_parts))

            if metadata is not False:
                metadata_parts = []
                if metadata or self.post is not None or self.dev is not None:
                    metadata_parts.append(self.commit)
                if dirty and self.dirty:
                    metadata_parts.append("dirty")
                metadata_segment = ".".join(x for x in metadata_parts if x is not None)
                if metadata_segment:
                    out += "+{}".format(metadata_segment)
        elif style == Style.Pvp:
            out += self.base

            pre_parts = []
            if self.epoch is not None:
                pre_parts.append(("epoch", self.epoch))
            if self.pre_type is not None and self.pre_number is not None:
                pre_parts.append((self.pre_type, self.pre_number))
            if self.post is not None:
                pre_parts.append(("post", self.post))
            if self.dev is not None:
                pre_parts.append(("dev", self.dev))
            if pre_parts:
                out += "-{}".format("-".join("{}-{}".format(k, v) for k, v in pre_parts))

            if metadata is not False:
                metadata_parts = []
                if metadata or self.post is not None or self.dev is not None:
                    metadata_parts.append(self.commit)
                if dirty and self.dirty:
                    metadata_parts.append("dirty")
                metadata_segment = "-".join(x for x in metadata_parts if x is not None)
                if metadata_segment:
                    out += "-{}".format(metadata_segment)

        check_version(out, style)
        return out

    @classmethod
    def from_git(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
        r"""
        Determine a version based on Git tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        """
        code, msg = _run_cmd('git log -n 1 --format="format:%h"', codes=[0, 128])
        if code == 128:
            return cls("0.0.0", post=0, dev=0, dirty=True)
        commit = msg

        code, msg = _run_cmd("git describe --always --dirty")
        dirty = msg.endswith("-dirty")

        code, msg = _run_cmd("git tag --merged HEAD --sort -creatordate")
        if not msg:
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
        tags = msg.splitlines()
        tag, base, pre = _match_version_pattern(pattern, tags, latest_tag)

        code, msg = _run_cmd("git rev-list --count {}..HEAD".format(tag))
        distance = int(msg)

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=bool(dirty))

    @classmethod
    def from_mercurial(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
        r"""
        Determine a version based on Mercurial tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        """
        code, msg = _run_cmd("hg summary")
        dirty = "commit: (clean)" not in msg.splitlines()

        code, msg = _run_cmd('hg id --template "{id|short}"')
        commit = msg if set(msg) != {"0"} else None

        code, msg = _run_cmd(
            'hg log -r "sort(tag(){}, -rev)" --template "{{join(tags, \':\')}}\\n"'.format(
                " and ancestors({})".format(commit) if commit is not None else ""
            )
        )
        if not msg:
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
        tags = [tag for tags in [line.split(":") for line in msg.splitlines()] for tag in tags]
        tag, base, pre = _match_version_pattern(pattern, tags, latest_tag)

        code, msg = _run_cmd('hg log -r "{0}::{1} - {0}" --template "."'.format(tag, commit))
        # The tag itself is in the list, so offset by 1.
        distance = len(msg) - 1

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=dirty)

    @classmethod
    def from_darcs(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
        r"""
        Determine a version based on Darcs tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        """
        code, msg = _run_cmd("darcs status", codes=[0, 1])
        dirty = msg != "No changes!"

        code, msg = _run_cmd("darcs log --last 1")
        commit = msg.split()[1].strip() if msg else None

        code, msg = _run_cmd("darcs show tags")
        if not msg:
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
        tags = msg.splitlines()
        tag, base, pre = _match_version_pattern(pattern, tags, latest_tag)

        code, msg = _run_cmd("darcs log --from-tag {} --count".format(tag))
        # The tag itself is in the list, so offset by 1.
        distance = int(msg) - 1

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=dirty)

    @classmethod
    def from_subversion(
        cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False, tag_dir: str = "tags"
    ) -> "Version":
        r"""
        Determine a version based on Subversion tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        :param tag_dir: Location of tags relative to the root.
        """
        tag_dir = tag_dir.strip("/")

        code, msg = _run_cmd("svn status")
        dirty = bool(msg)

        code, msg = _run_cmd("svn info --show-item url")
        url = msg.strip("/")

        code, msg = _run_cmd("svn info --show-item last-changed-revision")
        if not msg or msg == "0":
            commit = None
        else:
            commit = msg

        if not commit:
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
        code, msg = _run_cmd('svn ls -v -r {} "{}/{}"'.format(commit, url, tag_dir))
        lines = [line.split(maxsplit=5) for line in msg.splitlines()[1:]]
        tags_to_revs = {line[-1].strip("/"): int(line[0]) for line in lines}
        if not tags_to_revs:
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
        tags_to_sources_revs = {}
        for tag, rev in tags_to_revs.items():
            code, msg = _run_cmd('svn log -v "{}/{}/{}" --stop-on-copy'.format(url, tag_dir, tag))
            for line in msg.splitlines():
                match = re.search(r"A /{}/{} \(from .+?:(\d+)\)".format(tag_dir, tag), line)
                if match:
                    source = int(match.group(1))
                    tags_to_sources_revs[tag] = (source, rev)
        tags = sorted(tags_to_sources_revs, key=lambda x: tags_to_sources_revs[x], reverse=True)
        tag, base, pre = _match_version_pattern(pattern, tags, latest_tag)

        source, rev = tags_to_sources_revs[tag]
        # The tag itself is in the list, so offset by 1.
        distance = int(commit) - 1 - source

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=dirty)

    @classmethod
    def from_bazaar(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
        r"""
        Determine a version based on Bazaar tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        """
        code, msg = _run_cmd("bzr status")
        dirty = msg != ""

        code, msg = _run_cmd("bzr log --limit 1 --line")
        commit = msg.split(":", 1)[0] if msg else None

        code, msg = _run_cmd("bzr tags")
        if not msg or not commit:
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
        tags_to_revs = {
            line.split()[0]: int(line.split()[1])
            for line in msg.splitlines()
            if line.split()[1] != "?"
        }
        tags = [x[1] for x in sorted([(v, k) for k, v in tags_to_revs.items()], reverse=True)]
        tag, base, pre = _match_version_pattern(pattern, tags, latest_tag)

        distance = int(commit) - tags_to_revs[tag]

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=dirty)

    @classmethod
    def from_fossil(cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False) -> "Version":
        r"""
        Determine a version based on Fossil tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        :param latest_tag: If true, only inspect the latest tag for a pattern
            match. If false, keep looking at tags until there is a match.
        """
        code, msg = _run_cmd("fossil changes --differ", codes=[0, 1])
        if code == 1:
            return cls("0.0.0", post=0, dev=0, dirty=True)
        dirty = bool(msg)

        code, msg = _run_cmd(
            "fossil sql \"SELECT value FROM vvar WHERE name = 'checkout-hash' LIMIT 1\""
        )
        commit = msg.strip("'")

        code, msg = _run_cmd("fossil sql \"SELECT count() FROM event WHERE type = 'ci'\"")
        if int(msg) <= 1:
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)

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
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)

        tags_to_distance = [
            (line.rsplit(",", 1)[0][5:-1], int(line.rsplit(",", 1)[1]) - 1)
            for line in msg.splitlines()
        ]
        tag, base, pre = _match_version_pattern(
            pattern, [t for t, d in tags_to_distance], latest_tag
        )
        distance = dict(tags_to_distance)[tag]

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=bool(dirty))

    @classmethod
    def from_any_vcs(
        cls, pattern: str = _VERSION_PATTERN, latest_tag: bool = False, tag_dir: str = "tags"
    ) -> "Version":
        """
        Determine a version based on a detected version control system.

        :param pattern: Regular expression matched against the version source.
            The default value defers to the VCS-specific `from_` functions.
        :param latest_tag: If true, only inspect the latest tag on the latest
            tagged commit for a pattern match. If false, keep looking at tags
            until there is a match.
        :param tag_dir: Location of tags relative to the root.
            This is only used for Subversion.
        """
        checks = [
            (Vcs.Git, "git status"),
            (Vcs.Mercurial, "hg status"),
            (Vcs.Darcs, "darcs log"),
            (Vcs.Subversion, "svn log"),
            (Vcs.Bazaar, "bzr status"),
            (Vcs.Fossil, "fossil status"),
        ]
        for vcs, command in checks:
            if shutil.which(command.split()[0]):
                code, _ = _run_cmd(command, codes=[])
                if code == 0:
                    return cls._do_vcs_callback(vcs, pattern, latest_tag, tag_dir)
        raise RuntimeError("Unable to detect version control system.")

    @classmethod
    def from_vcs(
        cls,
        vcs: Vcs,
        pattern: str = _VERSION_PATTERN,
        latest_tag: bool = False,
        tag_dir: str = "tags",
    ) -> "Version":
        """
        Determine a version based on a specific VCS setting.

        This is primarily intended for other tools that want to generically
        use some VCS setting based on user configuration, without having to
        maintain a mapping from the VCS name to the appropriate function.

        :param pattern: Regular expression matched against the version source.
            The default value defers to the VCS-specific `from_` functions.
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
    failure_message = "Version '{}' does not conform to the {} style".format(version, name)
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
    Check pkg_resources info or a fallback function to determine the version.
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
        return Version(pkg_resources.get_distribution(name).version)
    except pkg_resources.DistributionNotFound:
        pass

    if third_choice:
        third_ver = third_choice()
        if third_ver:
            return third_ver

    return fallback


__version__ = get_version(
    "dunamai",
    first_choice=lambda: Version.from_git() if "DUNAMAI_DEV" in os.environ else None,
    third_choice=Version.from_git,
).serialize()
