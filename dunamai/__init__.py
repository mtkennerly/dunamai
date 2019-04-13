__all__ = ["get_version", "Style", "Version"]

import os
import pkg_resources
import re
import subprocess
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import Callable, Optional, Tuple

_VERSION_PATTERN = r"v(?P<base>\d+\.\d+\.\d+)((?P<pre_type>[a-zA-Z]+)(?P<pre_number>\d+))?"
# PEP 440: [N!]N(.N)*[{a|b|rc}N][.postN][.devN][+<local version label>]
_VALID_PEP440 = r"^(\d!)?\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+.+)?$"
_VALID_SEMVER = (
    r"^\d+\.\d+\.\d+(\-[a-zA-z0-9\-]+(\.[a-zA-z0-9\-]+)*)?(\+[a-zA-z0-9\-]+(\.[a-zA-z0-9\-]+)?)?$"
)
_VALID_PVP = r"^\d+(\.\d+)*(-[a-zA-Z0-9]+)*$"


def _run_cmd(command: str, where: Path = None) -> Tuple[int, str]:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(where) if where is not None else None,
    )
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
        self,
        with_metadata: bool = None,
        with_dirty: bool = False,
        format: str = None,
        style: Style = None,
    ) -> str:
        """
        Create a string from the version info.

        :param with_metadata: Metadata (commit, dirty) is normally included in
            the local version part if post or dev are set. Set this to True to
            always include metadata, or set it to False to always exclude it.
        :param with_dirty: Set this to True to include a dirty flag in the
            metadata if applicable. Inert when with_metadata=False.
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

            if with_metadata is not False:
                metadata_parts = []
                if with_metadata or self.post is not None or self.dev is not None:
                    metadata_parts.append(self.commit)
                if with_dirty and self.dirty:
                    metadata_parts.append("dirty")
                metadata = ".".join(x for x in metadata_parts if x is not None)
                if metadata:
                    out += "+{}".format(metadata)
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

            if with_metadata is not False:
                metadata_parts = []
                if with_metadata or self.post is not None or self.dev is not None:
                    metadata_parts.append(self.commit)
                if with_dirty and self.dirty:
                    metadata_parts.append("dirty")
                metadata = ".".join(x for x in metadata_parts if x is not None)
                if metadata:
                    out += "+{}".format(metadata)
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

            if with_metadata is not False:
                metadata_parts = []
                if with_metadata or self.post is not None or self.dev is not None:
                    metadata_parts.append(self.commit)
                if with_dirty and self.dirty:
                    metadata_parts.append("dirty")
                metadata = "-".join(x for x in metadata_parts if x is not None)
                if metadata:
                    out += "-{}".format(metadata)

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
        if not re.search(pattern, serialized):
            raise ValueError(
                "Version '{}' does not conform to the {} style".format(serialized, name)
            )

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
        code, description = _run_cmd("git describe --tags --long --dirty")
        if code == 128:
            code, description = _run_cmd("git describe --always --dirty")
            if code == 128:
                return cls("0.0.0", post=0, dev=0, dirty=True)
            elif code == 0:
                commit, *dirty = description.split("-")
                return cls("0.0.0", post=0, dev=0, commit=commit, dirty=bool(dirty))
            else:
                raise RuntimeError("Git returned code {}".format(code))
        elif code == 0:
            tag, raw_distance, commit, *dirty = description.split("-")
            distance = int(raw_distance)
        else:
            raise RuntimeError("Git returned code {}".format(code))

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
        if code == 0:
            dirty = "commit: (clean)" not in msg.splitlines()
        else:
            raise RuntimeError("Mercurial returned code {}".format(code))

        code, description = _run_cmd("hg id")
        if code == 0:
            commit = description.split()[0].strip("+")  # type: Optional[str]
            if commit and set(commit) == {"0"}:
                commit = None
        else:
            raise RuntimeError("Mercurial returned code {}".format(code))

        code, description = _run_cmd('hg parent --template "{latesttag} {latesttagdistance}"')
        if code == 0:
            if not description or description.split()[0] == "null":
                return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
            tag, raw_distance = description.split()
            # Distance is 1 immediately after creating tag.
            distance = int(raw_distance) - 1
        else:
            raise RuntimeError("Mercurial returned code {}".format(code))

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
        code, msg = _run_cmd("darcs status")
        if code in [0, 1]:
            dirty = msg != "No changes!"
        else:
            raise RuntimeError("Darcs returned code {}".format(code))

        code, description = _run_cmd("darcs log --last 1")
        if code == 0:
            if not description:
                commit = None
            else:
                commit = description.split()[1].strip()
        else:
            raise RuntimeError("Darcs returned code {}".format(code))

        code, description = _run_cmd("darcs show tags")
        if code == 0:
            if not description:
                return cls("0.0.0", post=0, dev=0, commit=commit, dirty=dirty)
            tag = description.split()[0]
        else:
            raise RuntimeError("Darcs returned code {}".format(code))

        code, description = _run_cmd("darcs log --from-tag {}".format(tag))
        if code == 0:
            # The tag itself is in the list, so offset by 1.
            distance = -1
            for line in description.splitlines():
                if line.startswith("patch "):
                    distance += 1
        else:
            raise RuntimeError("Darcs returned code {}".format(code))

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
        vcs = _find_higher_dir(".git", ".hg", "_darcs")
        if not vcs:
            raise RuntimeError("Unable to detect version control system.")

        callbacks = {".git": cls.from_git, ".hg": cls.from_mercurial, "_darcs": cls.from_darcs}

        arguments = []
        if pattern:
            arguments.append(pattern)

        return callbacks[vcs](*arguments)


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
