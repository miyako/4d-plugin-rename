"""Run literal release shell blocks with a closed PATH and native-tool stubs."""

import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/release.yml").read_text()
SPEC = importlib.util.spec_from_file_location(
    "native_source_version", ROOT / ".github/scripts/source_version.py"
)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)
PWSH = shutil.which("pwsh") or (
    "/usr/local/bin/pwsh" if Path("/usr/local/bin/pwsh").is_file() else None
)


def step(name):
    matches = re.findall(
        rf"^      - name: {re.escape(name)}\n"
        r"(?:(?!      - ).*\n)*?        run: \|\n"
        r"((?:          .*(?:\n|$)|[ \t]*\n)+)",
        WORKFLOW, re.MULTILINE,
    )
    if len(matches) != 1:
        raise AssertionError(f"Expected one literal run block for {name!r}")
    return textwrap.dedent(matches[0])


STUB = r'''
import json
import os
from pathlib import Path
import plistlib
import sys

tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps([tool, *args]) + "\n")
contents = Path(os.environ["TEST_BUNDLE"]) / "Contents"
mode = os.environ.get("BUILD_MODE", "complete")
if tool == "xcodebuild":
    for path in (
        contents / "MacOS/RENAME", contents / "Info.plist",
        contents / "Resources/English.lproj/InfoPlist.strings",
        contents / "_CodeSignature", contents.parent.parent / "Default",
        contents.parent.parent / "RENAME.build", Path("build"),
    ):
        assert not path.exists(), "stale output survived: " + str(path)
    if mode == "fail":
        sys.exit(70)
    if mode != "missing-binary":
        (contents / "MacOS").mkdir(parents=True, exist_ok=True)
        (contents / "MacOS/RENAME").write_bytes(b"rebuilt-universal")
    if mode != "missing-plist":
        data = plistlib.loads(Path("Info.plist").read_bytes())
        if mode == "stale-plist":
            data["CFBundleShortVersionString"] = os.environ["STALE_VERSION"]
        if mode == "stale-build-version":
            data["CFBundleVersion"] = os.environ["STALE_VERSION"]
        (contents / "Info.plist").write_bytes(plistlib.dumps(data))
    if mode != "missing-localized":
        data = Path("English.lproj/InfoPlist.strings").read_bytes()
        if mode == "stale-localized":
            data = data.replace(os.environ["SOURCE_VERSION"].encode(),
                                os.environ["STALE_VERSION"].encode())
        target = contents / "Resources/English.lproj/InfoPlist.strings"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
elif tool == "lipo":
    binary = os.environ["TEST_BUNDLE"] + "/Contents/MacOS/RENAME"
    assert Path(binary).is_file()
    architectures = os.environ.get("ARCHS", "arm64 x86_64")
    if args == ["-info", binary]:
        print("Architectures in the fat file: " + architectures)
    else:
        assert args == ["-verify_arch", "arm64", "x86_64", binary]
        if not {"arm64", "x86_64"}.issubset(architectures.split()):
            sys.exit(75)
elif tool == "python3":
    assert args == [".github/scripts/source_version.py", "--verify-bundle",
                    os.environ["TEST_BUNDLE"]]
    os.execv(os.environ["REAL_PYTHON"], [os.environ["REAL_PYTHON"], *args])
elif tool == "security":
    assert args == ["find-identity", "-v", "-p", "codesigning", os.environ["KEYCHAIN_PATH"]]
    if os.environ.get("SIGN_MODE") != "missing-identity":
        print('1) FAKE "Developer ID Application: Fixture (TEST)"')
elif tool == "codesign":
    verify = args[0] == "--verify"
    expected = (["--verify", "--deep", "--strict", "--verbose=2"] if verify else
                ["--verbose", "--deep", "--timestamp", "--force", "--options=runtime",
                 "--sign", "Developer ID Application: Fixture (TEST)"])
    assert args == [*expected, os.environ["BUNDLE_PATH"]]
    if os.environ.get("SIGN_MODE") == ("verify" if verify else "sign"):
        sys.exit(76)
elif tool in ("ditto", "hdiutil"):
    assert Path(os.environ["BUNDLE_PATH"]).is_dir()
    expected = (["-c", "-k", "--keepParent", os.environ["BUNDLE_PATH"]] if tool == "ditto"
                else ["create", "-format", "UDBZ", "-volname", "RENAME", "-srcfolder",
                      os.environ["BUNDLE_PATH"]])
    assert args[:-1] == expected
    if os.environ.get("PACKAGE_FAIL") == tool:
        sys.exit(77)
    Path(args[-1]).write_bytes(b"stub archive")
elif tool == "xcrun":
    scenario = os.environ.get("NOTARY_MODE", "accepted")
    if args[:2] == ["notarytool", "submit"]:
        assert args[3:] == [
            "--keychain-profile", "notarytool-profile", "--keychain",
            os.environ["KEYCHAIN_PATH"], "--wait", "--output-format", "json"
        ]
        assert Path(args[2]).is_file()
        second = args[2].endswith(".dmg")
        if scenario in ("transport", "accepted-nonzero") or (
            scenario == "second-transport" and second
        ):
            print(json.dumps({"status": "Accepted"}))
            sys.exit(71)
        if scenario == "malformed":
            print("not JSON")
        elif scenario == "missing-status":
            print("{}")
        else:
            status = "Invalid" if (
                scenario == "invalid" or (scenario == "second-invalid" and second)
            ) else "In Progress" if scenario == "pending" else "Accepted"
            print(json.dumps({"id": "submission", "status": status}))
    else:
        assert args == ["stapler", "staple",
                        "RENAME-" + os.environ["SOURCE_VERSION"] + ".dmg"]
        if scenario == "staple":
            sys.exit(73)
elif tool == "plutil":
    assert args == ["-extract", "status", "raw", "-o", "-", "-"]
    try:
        value = json.load(sys.stdin)["status"]
        assert isinstance(value, str)
        print(value)
    except (ValueError, KeyError, AssertionError):
        sys.exit(74)
else:
    raise AssertionError("Unexpected tool: " + tool)
'''


class NativeShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".native-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in (*source.SOURCE_PATHS, Path(".github/scripts/source_version.py")):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
        self.version = source.read(self.root)
        major, minor, patch = map(int, self.version.split("."))
        self.stale = f"{major}.{minor}.{patch + 1}"
        self.relative_bundle = "test/Plugins/RENAME.bundle"
        self.bundle = self.root / self.relative_bundle
        self.contents = self.bundle / "Contents"
        self.log = self.root / "calls.jsonl"
        self.env_file = self.root / "github-env"
        self.env_file.touch()
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        for name in ("xcodebuild", "lipo", "python3", "ditto", "hdiutil", "xcrun",
                     "plutil", "security", "codesign"):
            executable = self.bin / name
            executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent(STUB))
            executable.chmod(0o755)
        for name in ("rm", "ls", "grep", "head", "sed", "mkdir", "cp"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            (self.bin / name).symlink_to(executable)
        self.env = {
            "PATH": str(self.bin), "CALL_LOG": str(self.log),
            "REAL_PYTHON": sys.executable, "PYTHONDONTWRITEBYTECODE": "1",
            "SOURCE_VERSION": self.version, "STALE_VERSION": self.stale,
            "TEST_BUNDLE": self.relative_bundle, "BUNDLE_PATH": self.relative_bundle,
            "KEYCHAIN_PATH": str(self.root / "fake.keychain-db"),
            "GITHUB_ENV": str(self.env_file),
        }
        self.preserved = {}
        for relative in (
            "QuickLook/Thumbnail.png", "Windows/RENAME.4DX", "Windows64/RENAME.4DX",
            "Resources/manifest.json", "Resources/constants.xlf",
        ):
            data = (ROOT / self.relative_bundle / "Contents" / relative).read_bytes()
            self.write(relative, data)
            self.preserved[relative] = data
        for relative in ("MacOS/RENAME", "Info.plist",
                         "Resources/English.lproj/InfoPlist.strings",
                         "_CodeSignature/CodeResources"):
            self.write(relative, b"stale build output")
        for relative in ("test/Plugins/Default/stale", "test/Plugins/RENAME.build/stale",
                         "build/stale"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"stale intermediate")

    def write(self, relative, data):
        path = self.contents / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run_step(self, name, **env):
        script = step(name)
        for key, value in {
            "env.PRODUCT_NAME": "RENAME", "env.BASE_DIR": "test",
            "env.MACOS_DEPLOYMENT_TARGET": "11.0",
            "needs.version.outputs.version": self.version,
        }.items():
            script = script.replace("${{ " + key + " }}", value)
        self.assertNotIn("${{", script)
        return subprocess.run(
            ["/bin/bash", "-c", script], cwd=self.root, env={**self.env, **env},
            text=True, capture_output=True, timeout=30,
        )

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def calls(self, tool):
        return [call[1:] for line in self.log.read_text().splitlines()
                if (call := json.loads(line))[0] == tool] if self.log.exists() else []

    def build(self, **env):
        self.assert_ok(self.run_step("build macOS plugin (universal)", **env))

    def test_fresh_universal_build_preserves_resources_and_windows32(self):
        self.build()
        self.assertEqual((self.contents / "MacOS/RENAME").read_bytes(), b"rebuilt-universal")
        for relative, data in self.preserved.items():
            self.assertEqual((self.contents / relative).read_bytes(), data, relative)
        source.verify_bundle(self.bundle, self.root)
        self.assert_ok(self.run_step("verify universal binary"))
        self.assertEqual(len(self.calls("python3")), 1)
        self.assertEqual(self.calls("xcodebuild"), [[
            "-project", "RENAME.xcodeproj", "-target", "RENAME",
            "-configuration", "Default", "ARCHS=arm64 x86_64", "ONLY_ACTIVE_ARCH=NO",
            "MACOSX_DEPLOYMENT_TARGET=11.0", "CODE_SIGNING_ALLOWED=NO",
            f"CONFIGURATION_BUILD_DIR={self.root}/test/Plugins", "build",
        ]])

    def test_missing_rebuilt_products_cannot_reuse_committed_outputs(self):
        for mode, relative in (
            ("missing-binary", "MacOS/RENAME"), ("missing-plist", "Info.plist"),
            ("missing-localized", "Resources/English.lproj/InfoPlist.strings"),
        ):
            with self.subTest(mode=mode):
                self.build(BUILD_MODE=mode)
                self.assertFalse((self.contents / relative).exists())
                self.assertNotEqual(self.run_step("verify universal binary").returncode, 0)

    def test_stale_rebuilt_versions_are_rejected(self):
        for mode in ("stale-plist", "stale-build-version", "stale-localized"):
            with self.subTest(mode=mode):
                self.build(BUILD_MODE=mode)
                result = self.run_step("verify universal binary")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("differs from selected source", result.stderr)

    def test_both_exact_architectures_required_and_i386_explicitly_rejected(self):
        self.build()
        for architectures in (
            "arm64", "x86_64", "arm64e x86_64", "arm64 x86_64h", "arm64 x86_64 i386",
        ):
            with self.subTest(architectures=architectures):
                result = self.run_step("verify universal binary", ARCHS=architectures)
                self.assertNotEqual(result.returncode, 0)
                if "i386" in architectures:
                    self.assertIn("i386 slice found", result.stdout)
        self.assertEqual(self.calls("python3"), [])

    def test_cleanup_failure_stops_before_build(self):
        executable = self.bin / "rm"
        executable.unlink()
        executable.write_text("#!/bin/bash\nexit 79\n")
        executable.chmod(0o755)
        self.assertNotEqual(self.run_step("build macOS plugin (universal)").returncode, 0)
        self.assertEqual(self.calls("xcodebuild"), [])
        self.assertEqual((self.contents / "MacOS/RENAME").read_bytes(), b"stale build output")

    def test_build_failure_is_fatal(self):
        self.assertNotEqual(
            self.run_step("build macOS plugin (universal)", BUILD_MODE="fail").returncode, 0
        )

    def test_exact_windows_artifact_required_not_nested_stale_match(self):
        artifact = self.root / "winbuild/RENAME.4DX"
        nested = artifact.parent / "stale/RENAME.4DX"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"stale recursive match")
        for data in (None, b""):
            if data is not None:
                artifact.write_bytes(data)
            result = self.run_step("merge Windows binaries into the bundle")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact artifact path", result.stdout)
            self.assertEqual(self.env_file.read_text(), "")
        artifact.write_bytes(b"fresh selected-source Windows binary")
        self.assert_ok(self.run_step("merge Windows binaries into the bundle"))
        self.assertEqual((self.contents / "Windows64/RENAME.4DX").read_bytes(),
                         artifact.read_bytes())
        self.assertEqual(self.env_file.read_text(), f"BUNDLE_PATH={self.relative_bundle}\n")
        self.assertEqual((self.contents / "Windows/RENAME.4DX").read_bytes(),
                         self.preserved["Windows/RENAME.4DX"])

    def test_signing_requires_identity_sign_and_strict_verification(self):
        self.assert_ok(self.run_step("codesign"))
        self.assertEqual(len(self.calls("codesign")), 2)
        for scenario, count in (("missing-identity", 0), ("sign", 1), ("verify", 2)):
            with self.subTest(scenario=scenario):
                self.log.unlink()
                self.assertNotEqual(self.run_step("codesign", SIGN_MODE=scenario).returncode, 0)
                self.assertEqual(len(self.calls("codesign")), count)
                self.assertEqual(self.calls("xcrun"), [])

    def test_compiled_localized_versions_are_verified(self):
        self.build()
        values = dict(re.findall(
            r'(?m)^(\w+)\s*=\s*"([^"]*)";', source.text(self.root / source.LOCALIZED)
        ))
        self.assertEqual(values["CFBundleShortVersionString"], self.version)
        for fmt in (plistlib.FMT_BINARY, plistlib.FMT_XML):
            with self.subTest(fmt=fmt):
                self.write("Resources/English.lproj/InfoPlist.strings",
                           plistlib.dumps(values, fmt=fmt))
                self.assert_ok(self.run_step("verify universal binary"))
                for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
                    stale = {**values, key: values[key].replace(self.version, self.stale)}
                    self.write("Resources/English.lproj/InfoPlist.strings",
                               plistlib.dumps(stale, fmt=fmt))
                    self.assertNotEqual(self.run_step("verify universal binary").returncode, 0)

    def test_xcode_utf16_localized_versions_are_verified(self):
        self.build()
        original = source.text(self.root / source.LOCALIZED)
        for encoding, prefix in (("utf-16", b""), ("utf-16-be", b"\xfe\xff")):
            with self.subTest(encoding=encoding):
                for stale in (False, True):
                    value = original.replace(self.version, self.stale) if stale else original
                    self.write("Resources/English.lproj/InfoPlist.strings",
                               prefix + value.encode(encoding))
                    result = self.run_step("verify universal binary")
                    if stale:
                        self.assertNotEqual(result.returncode, 0)
                    else:
                        self.assert_ok(result)

    def test_both_accepted_submissions_then_staple_and_export(self):
        self.assert_ok(self.run_step("package, notarize & staple"))
        calls = self.calls("xcrun")
        self.assertEqual([call[2] for call in calls[:2]],
                         [f"RENAME-{self.version}.zip", f"RENAME-{self.version}.dmg"])
        self.assertEqual(calls[-1], ["stapler", "staple", f"RENAME-{self.version}.dmg"])
        self.assertEqual(self.env_file.read_text().splitlines(), [
            f"ZIP_PATH=RENAME-{self.version}.zip", f"DMG_PATH=RENAME-{self.version}.dmg",
        ])

    def test_notary_failures_block_staple_and_publication_paths(self):
        for scenario in (
            "transport", "accepted-nonzero", "invalid", "pending", "malformed",
            "missing-status", "second-transport", "second-invalid", "staple",
        ):
            with self.subTest(scenario=scenario):
                self.log.unlink(missing_ok=True)
                result = self.run_step("package, notarize & staple", NOTARY_MODE=scenario)
                self.assertNotEqual(result.returncode, 0)
                calls = self.calls("xcrun")
                submissions = [call for call in calls if call[:2] == ["notarytool", "submit"]]
                self.assertEqual(len(submissions), 2 if scenario.startswith("second-")
                                 or scenario == "staple" else 1)
                self.assertEqual(len([c for c in calls if c[:2] == ["stapler", "staple"]]),
                                 1 if scenario == "staple" else 0)
                self.assertEqual(self.env_file.read_text(), "")

    def test_packaging_failure_blocks_notarization(self):
        for tool in ("ditto", "hdiutil"):
            with self.subTest(tool=tool):
                self.assertNotEqual(
                    self.run_step("package, notarize & staple", PACKAGE_FAIL=tool).returncode, 0
                )
                self.assertEqual(self.calls("xcrun"), [])
                self.assertEqual(self.env_file.read_text(), "")


class NativeConfigurationTests(unittest.TestCase):
    def test_manual_immutable_source_and_serial_publication(self):
        self.assertRegex(WORKFLOW, r"(?m)^name: Build$")
        trigger = WORKFLOW.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(trigger.strip(), "workflow_dispatch:")
        self.assertIn("group: release-publication\n  cancel-in-progress: false", WORKFLOW)
        self.assertEqual(WORKFLOW.count("uses: actions/checkout@v4"), 3)
        self.assertEqual(WORKFLOW.count("ref: ${{ github.sha }}"), 3)
        self.assertIn('release.py preflight --sha "$SELECTED_SHA"',
                      step("validate source and publication availability"))
        self.assertIn('release.py publish --sha "$SELECTED_SHA" "$ZIP_PATH" "$DMG_PATH"',
                      step("create GitHub Release"))
        self.assertEqual(WORKFLOW.count("GH_TOKEN: ${{ github.token }}"), 2)
        self.assertEqual(WORKFLOW.count("SELECTED_SHA: ${{ github.sha }}"), 2)
        for output in ("tag", "version"):
            self.assertIn(f"{output}: ${{{{ steps.set.outputs.{output} }}}}", WORKFLOW)
        self.assertIn("needs: version", WORKFLOW)
        self.assertIn("needs: [version, build-windows]", WORKFLOW)
        self.assertNotIn("softprops/", WORKFLOW)
        self.assertNotIn("body:", WORKFLOW)
        self.assertLess(WORKFLOW.index("--verify-bundle"), WORKFLOW.index("- name: codesign"))
        self.assertLess(WORKFLOW.index("- name: package, notarize & staple"),
                        WORKFLOW.index("- name: create GitHub Release"))

    def test_exact_windows_output_matches_project_and_toolchain_is_preserved(self):
        project = ET.parse(ROOT / "RENAME.vcxproj")
        ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        condition = "'$(Configuration)|$(Platform)'=='Release|x64'"
        outdirs = [n.text for n in project.findall(".//m:OutDir", ns)
                   if n.get("Condition") == condition]
        extensions = [n.text for n in project.findall(".//m:TargetExt", ns)
                      if n.get("Condition") == condition]
        self.assertEqual(extensions, [".4DX"])
        self.assertEqual(len(outdirs), 1)
        actual = (outdirs[0].replace("$(ProjectDir)", "")
                  .replace("$(ProjectName)", "RENAME").replace("\\", "/") + "RENAME.4DX")
        normalize = step("normalize windows output to canonical case")
        match = re.search(r'^\$source = "([^"]+)"$', normalize, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(actual, match[1].replace("$base", "test").replace("$product", "RENAME"))
        self.assertNotIn("-Recurse", normalize)
        self.assertNotIn("SilentlyContinue", normalize)
        self.assertIn("$sourceResolved -ieq $destResolved", normalize)
        self.assertIn("/p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "
                      "/p:WindowsTargetPlatformVersion=10.0 /m", step("build x64"))
        self.assertIn("uses: microsoft/setup-msbuild@v2", WORKFLOW)
        self.assertIn("name: windows-binaries", WORKFLOW)
        self.assertIn("if-no-files-found: error", WORKFLOW)
        self.assertIn("path: winbuild", WORKFLOW)

    def test_original_macos_configuration_resources_and_secrets(self):
        project = (ROOT / source.PROJECT).read_text()
        for value in ("SDKROOT = macosx;", 'CLANG_CXX_LIBRARY = "libc++";',
                      "INFOPLIST_FILE = Info.plist;", "WRAPPER_EXTENSION = bundle;",
                      "English.lproj/InfoPlist.strings", "manifest.json in CopyFiles",
                      "constants.xlf in CopyFiles", "InfoPlist.strings in Resources"):
            self.assertIn(value, project)
        self.assertIn("MACOS_DEPLOYMENT_TARGET: '11.0'", WORKFLOW)
        self.assertIn("runs-on: windows-latest", WORKFLOW)
        self.assertIn("runs-on: macos-latest", WORKFLOW)
        self.assertEqual(set(re.findall(r"\$\{\{ secrets\.([A-Z_]+) \}\}", WORKFLOW)), {
            "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
            "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID",
            "NOTARYTOOL_PASSWORD",
        })


@unittest.skipUnless(PWSH, "PowerShell required for Windows shell harness")
class WindowsShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".windows-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "test/plugins/RENAME.bundle/contents/windows64/RENAME.4DX"
        self.binary.parent.mkdir(parents=True)

    def run_step(self, name, prefix=""):
        script = step(name)
        for key, value in (("PRODUCT_NAME", "RENAME"), ("BASE_DIR", "test")):
            script = script.replace("${{ env." + key + " }}", value)
        self.assertNotIn("${{", script)
        # Cmdlets need no external programs; never expose installed native tools.
        return subprocess.run(
            [PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", prefix + "\n" + script],
            cwd=self.root, env={**os.environ, "PATH": str(self.root)},
            text=True, capture_output=True, timeout=30,
        )

    def test_clean_invalidates_only_product_preserving_windows32_and_resources(self):
        self.binary.write_bytes(b"stale Windows binary")
        preserved = {}
        for relative in ("windows/RENAME.4DX", "Resources/manifest.json",
                         "Resources/constants.xlf", "QuickLook/Thumbnail.png"):
            path = self.binary.parent.parent / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"preserved committed data")
            preserved[path] = path.read_bytes()
        for relative in ("test/Plugins/Default/stale", "Objs/stale"):
            path = self.root / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(b"stale intermediate")
        for _ in range(2):
            result = self.run_step("clean stale outputs")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(self.binary.exists())
            self.assertFalse((self.root / "Objs").exists())
            self.assertFalse((self.root / "test/Plugins/Default").exists())
            for path, data in preserved.items():
                self.assertEqual(path.read_bytes(), data)

    def test_exact_nonempty_output_required_then_normalized_without_self_copy(self):
        stale = self.root / "stale/Plugins/RENAME.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"wrong recursive match")
        result = self.run_step("normalize windows output to canonical case")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exact MSBuild output", result.stderr)
        self.binary.write_bytes(b"")
        self.assertNotEqual(
            self.run_step("normalize windows output to canonical case").returncode, 0
        )
        self.binary.write_bytes(b"rebuilt Windows binary")
        result = self.run_step("normalize windows output to canonical case")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        canonical = self.root / "test/Plugins/RENAME.bundle/Contents/Windows64/RENAME.4DX"
        self.assertEqual(canonical.read_bytes(), b"rebuilt Windows binary")
        result = self.run_step("normalize windows output to canonical case")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cleanup_error_is_fatal(self):
        self.binary.write_bytes(b"stale Windows binary")
        result = self.run_step("clean stale outputs",
                               "function Remove-Item { Write-Error 'fixture cleanup failure' }")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture cleanup failure", result.stderr)
        self.assertEqual(self.binary.read_bytes(), b"stale Windows binary")

    def test_canonical_directory_error_is_fatal(self):
        self.binary.write_bytes(b"rebuilt Windows binary")
        result = self.run_step(
            "normalize windows output to canonical case",
            "function New-Item { Write-Error 'fixture directory failure' }",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture directory failure", result.stderr)


if __name__ == "__main__":
    unittest.main()
