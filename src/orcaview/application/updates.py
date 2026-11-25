"""Discover newer OrcaView releases and verified packages from the official repository."""

from dataclasses import dataclass
from hashlib import sha256
from http.client import HTTPException
import json
import platform
import re
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .update_tls import tls_context


_REPO = "lightzfpwings/OrcaView"
RELEASES_URL = f"https://github.com/{_REPO}/releases"
_API = f"https://api.github.com/repos/{_REPO}/releases"
_GITHUB_HOSTS = {"api.github.com", "github.com", "release-assets.githubusercontent.com",
                 "objects.githubusercontent.com", "github-releases.githubusercontent.com"}
_VERSION = re.compile(r"v?(\d{1,9})\.(\d{1,9})\.(\d{1,9})(?:(a|b|rc)(\d{1,9}))?", re.ASCII)
_STAGES = {"a": 0, "b": 1, "rc": 2, None: 3}
_SHA256 = re.compile(r"sha256:([a-fA-F0-9]{64})")
_INVALID_METADATA = "GitHub returned invalid release information."


class UpdateError(Exception):
    """The update check could not finish."""


@dataclass(frozen=True)
class UpdateAsset:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    page_url: str
    asset: Optional[UpdateAsset]


def _check_host(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc.lower() not in _GITHUB_HOSTS:
        raise URLError("Unexpected update server")


class _GitHubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_update_url(request: Request, *, timeout: float):
    """Open a GitHub request with certificate checks on every redirect."""
    _check_host(request.full_url)
    opener = build_opener(HTTPSHandler(context=tls_context()), _GitHubRedirect())
    return opener.open(request, timeout=timeout)


def _read(url, *, limit, cancelled, api=False):
    if cancelled is not None and cancelled():
        raise UpdateError("Update check canceled.")
    headers = {"User-Agent": "OrcaView-update-check"}
    if api:
        headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with open_update_url(Request(url, headers=headers), timeout=12) as response:
            data = response.read(limit + 1)
            if len(data) > limit:
                raise UpdateError("The GitHub release information exceeds the size limit.")
            return data, response.headers.get("Link", "")
    except HTTPError as exc:
        exc.close()
        raise UpdateError(f"GitHub returned HTTP {exc.code}.") from exc
    except (OSError, HTTPException) as exc:
        raise UpdateError(f"Could not read GitHub release information: {exc}") from exc


def _version_key(tag):
    match = _VERSION.fullmatch(tag)
    if match:
        major, minor, patch, stage, serial = match.groups()
        return int(major), int(minor), int(patch), _STAGES[stage], int(serial or 0)
    return None


def _releases(cancelled):
    page = 1
    while True:
        data, link = _read(f"{_API}?per_page=100&page={page}", limit=8 * 1024 * 1024,
                           cancelled=cancelled, api=True)
        try:
            releases = json.loads(data)
        except (ValueError, RecursionError) as exc:
            raise UpdateError(_INVALID_METADATA) from exc
        if not isinstance(releases, list):
            raise UpdateError(_INVALID_METADATA)
        for release in releases:
            if (not isinstance(release, dict) or not isinstance(release.get("tag_name"), str)
                    or not isinstance(release.get("draft"), bool)
                    or not isinstance(release.get("prerelease"), bool)):
                raise UpdateError(_INVALID_METADATA)
            yield release
        next_link = re.search(r'<([^>]+)>;\s*rel="next"', link)
        if next_link is None:
            return
        page += 1
        # GitHub may link using the numerical repository ID. Always request our fixed endpoint.
        if parse_qs(urlsplit(next_link[1]).query).get("page") != [str(page)]:
            raise UpdateError("GitHub returned invalid pagination information.")


def _platform_suffix(system, machine):
    os_name, arch = system.lower(), machine.lower()
    if os_name == "darwin" and arch in {"arm64", "aarch64"}:
        return "macOS-arm64.dmg"
    if arch in {"amd64", "x86_64"}:
        return {"windows": "Windows-x64-portable.zip", "linux": "Linux-x86_64.tar.gz"}.get(os_name)
    return None


def _asset_info(assets, tag, name):
    expected_url = f"{RELEASES_URL}/download/{tag}/{name}"
    for asset in assets:
        if (isinstance(asset, dict) and asset.get("name") == name and asset.get("state") == "uploaded"
                and asset.get("browser_download_url") == expected_url):
            return asset
    return None


def _manifest_hash(data, name):
    try:
        lines = data.decode("utf-8-sig").splitlines()
    except UnicodeError as exc:
        raise UpdateError("The checksum list published on GitHub is invalid.") from exc
    pattern = re.compile(r"([a-fA-F0-9]{64})\s+\*?(?:\./)?" + re.escape(name))
    matches = {m[1].lower() for line in lines if (m := pattern.fullmatch(line.strip()))}
    return matches.pop() if len(matches) == 1 else None


def _platform_asset(release, suffix, cancelled):
    if not suffix:
        return None
    tag = release["tag_name"]
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise UpdateError(_INVALID_METADATA)
    base = f"OrcaView-{tag.removeprefix('v')}"
    asset = _asset_info(assets, tag, f"{base}-{suffix}")
    if asset is None and suffix == "macOS-arm64.dmg":
        asset = _asset_info(assets, tag, f"{base}.{suffix}")
    if asset is None or type(asset.get("size")) is not int or asset["size"] <= 0:
        return None
    name = asset["name"]
    match = _SHA256.fullmatch(str(asset.get("digest", "")))
    if match:
        return UpdateAsset(name, asset["browser_download_url"], asset["size"], match[1].lower())
    for filename in ("SHA256UMS.txt", "SHA256SUMS.txt", "SHA256SUMS"):
        manifest = _asset_info(assets, tag, filename)
        if manifest:
            data, _ = _read(manifest["browser_download_url"], limit=512 * 1024, cancelled=cancelled)
            manifest_digest = _SHA256.fullmatch(str(manifest.get("digest", "")))
            if manifest_digest and sha256(data).hexdigest() != manifest_digest[1].lower():
                raise UpdateError("The checksum list published on GitHub is invalid.")
            checksum = _manifest_hash(data, name)
            if checksum:
                return UpdateAsset(name, asset["browser_download_url"], asset["size"], checksum)
    return None


def check_for_update(current_version: str, system: Optional[str] = None, machine: Optional[str] = None,
                     *, cancelled: Optional[Callable[[], bool]] = None) -> Optional[UpdateRelease]:
    """Find the highest eligible newer version, independent of GitHub's publication order."""
    current = _version_key(current_version)
    if current is None:
        raise UpdateError(f"Unrecognized OrcaView version: {current_version}")
    stable_channel = current[3] == _STAGES[None]
    highest = current
    newest = None
    for release in _releases(cancelled):
        if release["draft"]:
            continue
        key = _version_key(release["tag_name"])
        if key is None or key <= highest:
            continue
        if stable_channel and (release["prerelease"] or key[3] != _STAGES[None]):
            continue
        newest = release
        highest = key
    if newest is None:
        return None
    suffix = _platform_suffix(system or platform.system(), machine or platform.machine())
    tag = newest["tag_name"]
    return UpdateRelease(tag.removeprefix("v"), f"{RELEASES_URL}/tag/{tag}",
                         _platform_asset(newest, suffix, cancelled))
