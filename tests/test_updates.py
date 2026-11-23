import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from orcaview.application import updates


HASH = "1234abcd" * 8
MAC = "macOS-arm64.dmg"
LINUX = "Linux-x86_64.tar.gz"
WINDOWS = "Windows-x64-portable.zip"


class Response(io.BytesIO):
    def __init__(self, data, link=""):
        super().__init__(data if isinstance(data, bytes) else json.dumps(data).encode())
        self.headers = {"Link": link}


def asset(tag, name, digest="sha256:" + HASH):
    return {"name": name, "state": "uploaded", "size": 123, "digest": digest,
            "browser_download_url": f"{updates.RELEASES_URL}/download/{tag}/{name}"}


def release(tag, suffixes=(), *, preview=False, draft=False):
    return {"tag_name": tag, "prerelease": preview, "draft": draft,
            "assets": [asset(tag, f"OrcaView-{tag.removeprefix('v')}-{suffix}") for suffix in suffixes]}


class ReleaseUpdatesTest(unittest.TestCase):
    def check(self, releases, version="0.1.0a9", system="Darwin", machine="arm64"):
        with patch.object(updates, "open_update_url", return_value=Response(releases)) as request:
            result = updates.check_for_update(version, system, machine)
            self.assertEqual(request.call_count, 1)
            self.assertTrue(request.call_args.args[0].full_url.startswith(
                "https://api.github.com/repos/lightzfpwings/OrcaView/releases?"))
            return result

    def test_preview_orders_versions_and_can_upgrade_to_stable(self):
        releases = [release("v0.1.0b1"), release("v0.1.0a10", [MAC]), release("v0.1.0a9"),
                    release("v4.0.0", draft=True), release("daily")]
        self.assertEqual(self.check(releases).version, "0.1.0b1")
        self.assertEqual(self.check(releases[1:]).asset.sha256, HASH)
        self.assertEqual(self.check(releases + [release("v0.1.0rc3")]).version, "0.1.0rc3")
        self.assertEqual(self.check(releases + [release("v0.1.0")], "0.1.0rc4").version, "0.1.0")
        self.assertIsNone(self.check(releases[1:], "0.1.0a36"))

    def test_stable_skips_git_and_numeric_prereleases(self):
        data = [release("v0.2.0", preview=True), release("v1.0.0rc9"), release("v0.1.12")]
        self.assertEqual(self.check(data, "0.1.9").version, "0.1.12")
        self.assertIsNone(self.check(data, "0.1.12"))

    def test_platforms_match_only_compatible_package(self):
        data = [release("v0.1.0a10", [LINUX, MAC, WINDOWS, "languages.zip"])]
        for system, arch, suffix in [("Darwin", "arm64", MAC), ("Windows", "AMD64", WINDOWS),
                                     ("Linux", "x86_64", LINUX)]:
            with self.subTest(system=system):
                result = self.check(data, system=system, machine=arch)
                self.assertTrue(result.asset.name.endswith("-" + suffix))
                self.assertEqual(result.asset.size, 123)
        self.assertIsNone(self.check(data, system="Darwin", machine="x86_64").asset)
        self.assertIsNone(self.check(data, system="Linux", machine="aarch64").asset)

    def test_latest_on_later_page_can_lack_platform_asset(self):
        first = Response([release("v0.1.0a10", [MAC])],
                         '<https://api.github.com/repositories/123/releases?per_page=100&page=2>; rel="next"')
        second = Response([release("v0.1.0a12", [WINDOWS])])
        with patch.object(updates, "open_update_url", side_effect=[first, second]) as request:
            result = updates.check_for_update("0.1.0a9", "Darwin", "arm64")
        self.assertEqual(result.page_url, updates.RELEASES_URL + "/tag/v0.1.0a12")
        self.assertIsNone(result.asset)
        self.assertEqual(request.call_args.args[0].full_url,
                         "https://api.github.com/repos/lightzfpwings/OrcaView/releases?per_page=100&page=2")

    def test_manifest_fallback_requires_unambiguous_exact_filename(self):
        record = release("v0.1.0a10", [MAC])
        item = record["assets"][0]
        item["digest"] = None
        record["assets"].append(asset(record["tag_name"], "SHA256SUMS.txt", digest=None))
        name = item["name"]
        for lines, expected in [(f"{HASH.upper()}  {name}\r\n", HASH),
                                (f"{HASH} *{name}.bak\n", None),
                                (f"{HASH}  {name}\n{'f' * 64}  {name}\n", None)]:
            with self.subTest(lines=lines), patch.object(updates, "open_update_url",
                    side_effect=[Response([record]), Response(lines.encode())]) as request:
                found = updates.check_for_update("0.1.0a9", "Darwin", "arm64").asset
                self.assertEqual(found.sha256 if found else None, expected)
                self.assertEqual(request.call_args.args[0].full_url,
                                 record["assets"][-1]["browser_download_url"])

    def test_manifest_digest_must_match_when_supplied(self):
        record = release("v0.1.0a10", [MAC])
        item = record["assets"][0]
        item["digest"] = None
        record["assets"].append(asset(record["tag_name"], "SHA256SUMS.txt"))
        manifest = f"{HASH}  {item['name']}\n".encode()
        with patch.object(updates, "open_update_url", side_effect=[Response([record]), Response(manifest)]):
            with self.assertRaises(updates.UpdateError):
                updates.check_for_update("0.1.0a9", "Darwin", "arm64")

    def test_assets_require_official_versioned_url_upload_size_and_checksum(self):
        for change in [{"browser_download_url": "https://example.com/a"}, {"state": "open"},
                       {"size": 0}, {"size": True}, {"digest": "md5:test"}]:
            with self.subTest(change=change):
                data = release("v0.1.0a10", [MAC])
                data["assets"][0].update(change)
                self.assertIsNone(self.check([data]).asset)

    def test_api_and_pagination_failures_are_not_reported_as_up_to_date(self):
        next_loop = '<https://api.github.com/repositories/123/releases?page=1>; rel="next"'
        for reply in [Response({"message": "rate limit exceeded"}), Response(b"{}garbled"),
                      Response([{"tag_name": "v1.2.3"}]), Response([], next_loop),
                      HTTPError("https://api.github.com", 403, "Forbidden", {}, None), URLError("offline")]:
            with self.subTest(reply=reply), patch.object(updates, "open_update_url", side_effect=[reply]):
                with self.assertRaises(updates.UpdateError):
                    updates.check_for_update("0.1.0a9")

    def test_cancel_does_not_request_another_page(self):
        first = Response([], '<https://api.github.com/repositories/123/releases?page=2>; rel="next"')
        with patch.object(updates, "open_update_url", return_value=first) as request:
            with self.assertRaises(updates.UpdateError):
                updates.check_for_update("0.1.0a9", cancelled=iter([False, True]).__next__)
            self.assertEqual(request.call_count, 1)

    def test_transport_rejects_untrusted_hosts_and_plain_http(self):
        request = Request(updates.RELEASES_URL)
        for url in ["https://github.com.example.org/test", "http://github.com/test",
                    "https://github.com@evil.example/test", "file:///tmp/update"]:
            with self.subTest(url=url):
                with self.assertRaises(URLError):
                    updates.open_update_url(Request(url), timeout=1)
                with self.assertRaises(URLError):
                    updates._GitHubRedirect().redirect_request(request, None, 302, "", {}, url)
        cdn = "https://release-assets.githubusercontent.com/github-production-release-asset/123/abc"
        self.assertEqual(updates._GitHubRedirect().redirect_request(request, None, 302, "", {}, cdn).full_url, cdn)


if __name__ == "__main__":
    unittest.main()
