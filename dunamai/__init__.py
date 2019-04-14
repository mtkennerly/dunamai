__all__ = ["get_version", "Style", "Version"]

import os
import pkg_resources
import re
import subprocess
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

_VERSION_PATTERN = r"v(?P<base>\d+\.\d+\.\d+)((?P<pre_type>[a-zA-Z]+)(?P<pre_number>\d+))?"
# PEP 440: [N!]N(.N)*[{a|b|rc}N][.postN][.devN][+<local version label>]
_VALID_PEP440 = r"^(\d!)?\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+.+)?$"
_VALID_SEMVER = (
    r"^\d+\.\d+\.\d+(\-[a-zA-z0-9\-]+(\.[a-zA-z0-9\-]+)*)?(\+[a-zA-z0-9\-]+(\.[a-zA-z0-9\-]+)?)?$"
)
_VALID_PVP = r"^\d+(\.\d+)*(-[a-zA-Z0-9]+)*$"


def _run_cmd(command: str, codes: Sequence[int] = (0,), where: Path = None) -> Tuple[int, str]:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(where) if where is not None else None,
    )
    if codes and result.returncode not in codes:
        raise RuntimeError("The command '{}' returned code {}".format(command, result.returncode))
    return (result.returncode, result.stdout.decode().strip())


def _find_higher_dir(*names: str) -> Optional[str]:
    start = Path().resolve()
    for level in [start, *start.parents]:
        for name in names:
            if (level / name).is_dir():
                return name
    return None


def _match_version_pattern(pattern: str, source: str) -> Tuple[str, Optional[Tuple[str, int]]]:
    pattern_match = re.search(pattern, source)
    pre = None

    if pattern_match is None:
        raise ValueError("Pattern '{}' did not match the source '{}'".format(pattern, source))
    try:
        base = pattern_match.group("base")
    except IndexError:
        raise ValueError(
            "Pattern '{}' did not include required capture group 'base'".format(pattern)
        )

    try:
        pre_type = pattern_match.group("pre_type")
        pre_number = pattern_match.group("pre_number")
        if pre_type is not None and pre_number is not None:
            pre = (pre_type, int(pre_number))
    except IndexError:
        pass

    return (base, pre)


class Style(Enum):
    Pep440 = "pep440"
    SemVer = "semver"
    Pvp = "pvp"


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

    def __eq__(self, other) -> bool:
        if not isinstance(other, Version):
            raise TypeError(
                "Cannot compare Version with type {}".format(other.__class__.__qualname__)
            )
        return pkg_resources.parse_version(self.serialize()) == pkg_resources.parse_version(
            other.serialize()
        )

    def __lt__(self, other) -> bool:
        if not isinstance(other, Version):
            raise TypeError(
                "Cannot compare Version with type {}".format(other.__class__.__qualname__)
            )
        return pkg_resources.parse_version(self.serialize()) < pkg_resources.parse_version(
            other.serialize()
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

            def blank(value):
                return value if value is not None else ""

            out = format.format(
                base=self.base,
                epoch=blank(self.epoch),
                pre_type=blank(self.pre_type),
                pre_number=blank(self.pre_number),
                post=blank(self.post),
                dev=blank(self.dev),
                commit=blank(self.commit),
                dirty="dirty" if self.dirty else "clean",
            )
            if style is not None:
                self._validate(out, style)
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

        self._validate(out, style)
        return out

    def _validate(self, serialized: str, style: Style) -> None:
        if style is None:
            return
        groups = {
            Style.Pep440: ("PEP 440", _VALID_PEP440),
            Style.SemVer: ("Semantic Versioning", _VALID_SEMVER),
            Style.Pvp: ("PVP", _VALID_PVP),
        }
        name, pattern = groups[style]
        failure_message = "Version '{}' does not conform to the {} style".format(serialized, name)
        if not re.search(pattern, serialized):
            raise ValueError(failure_message)
        if style == Style.SemVer:
            parts = re.split(r"[.-]", serialized.split("+", 1)[0])
            if any(re.search(r"^0[0-9]+$", x) for x in parts):
                raise ValueError(failure_message)

    @classmethod
    def from_git(cls, pattern: str = _VERSION_PATTERN) -> "Version":
        r"""
        Determine a version based on Git tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        """
        code, msg = _run_cmd("git describe --tags --long --dirty", codes=[0, 128])
        if code == 128:
            code, msg = _run_cmd("git describe --always --dirty", codes=[0, 128])
            if code == 128:
                return cls("0.0.0", post=0, dev=0, dirty=True)
            else:
                commit, *dirty = msg.split("-")
                return cls("0.0.0", post=0, dev=0, commit=commit, dirty=bool(dirty))
        else:
            tag, raw_distance, commit, *dirty = msg.split("-")
            distance = int(raw_distance)

        base, pre = _match_version_pattern(pattern, tag)

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=bool(dirty))

    @classmethod
    def from_mercurial(cls, pattern: str = _VERSION_PATTERN) -> "Version":
        r"""
        Determine a version based on Mercurial tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        """
        code, msg = _run_cmd("hg summary")
        dirty = "commit: (clean)" not in msg.splitlines()

        code, msg = _run_cmd("hg id")
        commit = msg.split()[0].strip("+")  # type: Optional[str]
        if commit and set(commit) == {"0"}:
            commit = None

        code, msg = _run_cmd('hg parent --template "{latesttag} {latesttagdistance}"')
        if not msg or msg.split()[0] == "null":
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
        tag, raw_distance = msg.split()
        # Distance is 1 immediately after creating tag.
        distance = int(raw_distance) - 1

        base, pre = _match_version_pattern(pattern, tag)

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=dirty)

    @classmethod
    def from_darcs(cls, pattern: str = _VERSION_PATTERN) -> "Version":
        r"""
        Determine a version based on Darcs tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        """
        code, msg = _run_cmd("darcs status", codes=[0, 1])
        dirty = msg != "No changes!"

        code, msg = _run_cmd("darcs log --last 1")
        if not msg:
            commit = None
        else:
            commit = msg.split()[1].strip()

        code, msg = _run_cmd("darcs show tags")
        if not msg:
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
        tag = msg.split()[0]

        code, msg = _run_cmd("darcs log --from-tag {}".format(tag))
        # The tag itself is in the list, so offset by 1.
        distance = -1
        for line in msg.splitlines():
            if line.startswith("patch "):
                distance += 1

        base, pre = _match_version_pattern(pattern, tag)

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=dirty)

    @classmethod
    def from_subversion(cls, pattern: str = _VERSION_PATTERN, tag_dir: str = "tags") -> "Version":
        r"""
        Determine a version based on Subversion tags.

        :param pattern: Regular expression matched against the version source.
            This should contain one capture group named `base` corresponding to
            the release segment of the source, and optionally another two groups
            named `pre_type` and `pre_number` corresponding to the type (a, b, rc)
            and number of prerelease. For example, with a tag like v0.1.0, the
            pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
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
        code, msg = _run_cmd('svn ls -v "{}/{}"'.format(url, tag_dir))
        lines = [line.split(maxsplit=5) for line in msg.splitlines()[1:]]
        tags_revs = [(line[-1].strip("/"), int(line[0])) for line in lines]
        if not tags_revs:
            return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
        tags_revs_sources = []
        for tag, rev in tags_revs:
            code, msg = _run_cmd('svn log "{}/{}/{}" -v --stop-on-copy'.format(url, tag_dir, tag))
            for line in msg.splitlines():
                match = re.search(r"A /{}/{} \(from .+?:(\d+)\)".format(tag_dir, tag), line)
                if match:
                    source = int(match.group(1))
                    tags_revs_sources.append((tag, rev, source))
        tag, rev, source = sorted(tags_revs_sources, key=lambda info: (info[2], info[1]))[-1]

        # The tag itself is in the list, so offset by 1.
        distance = int(commit) - 1 - source

        base, pre = _match_version_pattern(pattern, tag)

        post = None
        dev = None
        if distance > 0:
            post = distance
            dev = 0

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=dirty)

    @classmethod
    def from_any_vcs(cls, pattern: str = None) -> "Version":
        """
        Determine a version based on a detected version control system.

        :param pattern: Regular expression matched against the version source.
            The default value defers to the VCS-specific `from_` functions.
        """
        vcs = _find_higher_dir(".git", ".hg", "_darcs", ".svn")

        arguments = []
        if pattern:
            arguments.append(pattern)

        if vcs == ".git":
            return cls.from_git(*arguments)
        elif vcs == ".hg":
            return cls.from_mercurial(*arguments)
        elif vcs == "_darcs":
            return cls.from_darcs(*arguments)
        elif vcs == ".svn":
            return cls.from_subversion(*arguments)
        else:
            raise RuntimeError("Unable to detect version control system.")


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
