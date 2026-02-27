from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from clawlite.skills.marketplace import (
    SkillMarketplaceError,
    build_auto_update_runtime_payload,
    install_skill,
    publish_skill,
    run_runtime_auto_update,
    schedule_auto_update,
    update_skills,
)


class MarketplaceFlowTests(unittest.TestCase):
    def _make_skill_zip(self, root: Path, slug: str, version: str, body: str) -> tuple[Path, str]:
        zip_path = root / f"{slug}-{version}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("SKILL.md", body)
            archive.writestr("meta.txt", f"{slug}:{version}")

        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        return zip_path, digest

    def _write_index(self, root: Path, entry: dict) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        index_path = root / "manifest.local.json"
        payload = {
            "schema_version": "1.0",
            "generated_at": "2026-02-27T00:00:00Z",
            "allow_hosts": ["raw.githubusercontent.com"],
            "skills": [entry],
        }
        index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return index_path

    def test_install_with_checksum_and_file_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_dir = root / "installed"
            manifest_path = root / "installed.json"

            archive, checksum = self._make_skill_zip(root, "demo", "1.0.0", "# demo v1")
            index = self._write_index(
                root,
                {
                    "slug": "demo",
                    "version": "1.0.0",
                    "description": "demo",
                    "download_url": archive.as_uri(),
                    "checksum_sha256": checksum,
                },
            )

            result = install_skill(
                "demo",
                index_url=index.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                allow_file_urls=True,
            )

            self.assertEqual(result["slug"], "demo")
            self.assertTrue((install_dir / "demo" / "SKILL.md").exists())
            installed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(installed_manifest["skills"]["demo"]["version"], "1.0.0")

    def test_install_blocks_non_allowlisted_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_dir = root / "installed"
            manifest_path = root / "installed.json"
            index = self._write_index(
                root,
                {
                    "slug": "blocked",
                    "version": "1.0.0",
                    "description": "blocked",
                    "download_url": "https://malicious.example/blocked.zip",
                    "checksum_sha256": "0" * 64,
                },
            )

            with self.assertRaises(SkillMarketplaceError):
                install_skill(
                    "blocked",
                    index_url=index.as_uri(),
                    install_dir=install_dir,
                    manifest_path=manifest_path,
                    allow_file_urls=True,
                )

    def test_update_flow_from_remote_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_dir = root / "installed"
            manifest_path = root / "installed.json"

            archive_v1, checksum_v1 = self._make_skill_zip(root, "demo", "1.0.0", "# demo v1")
            index_v1 = self._write_index(
                root / "v1",
                {
                    "slug": "demo",
                    "version": "1.0.0",
                    "description": "demo",
                    "download_url": archive_v1.as_uri(),
                    "checksum_sha256": checksum_v1,
                },
            )
            install_skill(
                "demo",
                index_url=index_v1.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                allow_file_urls=True,
            )

            archive_v2, checksum_v2 = self._make_skill_zip(root, "demo", "1.1.0", "# demo v2")
            index_v2 = self._write_index(
                root / "v2",
                {
                    "slug": "demo",
                    "version": "1.1.0",
                    "description": "demo",
                    "download_url": archive_v2.as_uri(),
                    "checksum_sha256": checksum_v2,
                },
            )

            result = update_skills(
                index_url=index_v2.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                allow_file_urls=True,
            )

            self.assertEqual(len(result["updated"]), 1)
            self.assertEqual(result["updated"][0]["slug"], "demo")
            self.assertEqual(result["updated"][0]["from_version"], "1.0.0")
            self.assertEqual(result["updated"][0]["version"], "1.1.0")

            body = (install_dir / "demo" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("v2", body)

    def test_publish_updates_local_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "my-skill"
            source_dir.mkdir(parents=True, exist_ok=True)
            (source_dir / "SKILL.md").write_text("# my skill", encoding="utf-8")
            (source_dir / "notes.txt").write_text("hello", encoding="utf-8")

            result = publish_skill(
                source_dir,
                slug="my-skill",
                version="2.0.0",
                description="test publish",
                hub_dir=root / "hub" / "marketplace",
                download_base_url="https://example.com/packages",
            )

            package_path = Path(result["package_path"])
            manifest_path = Path(result["manifest_path"])

            self.assertTrue(package_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["skills"]), 1)
            entry = manifest["skills"][0]
            self.assertEqual(entry["slug"], "my-skill")
            self.assertEqual(entry["version"], "2.0.0")
            self.assertEqual(entry["download_url"], "https://example.com/packages/my-skill-2.0.0.zip")

            checksum = hashlib.sha256(package_path.read_bytes()).hexdigest()
            self.assertEqual(entry["checksum_sha256"], checksum)

    def test_publish_rejects_invalid_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "my-skill"
            source_dir.mkdir(parents=True, exist_ok=True)
            (source_dir / "SKILL.md").write_text("# my skill", encoding="utf-8")

            with self.assertRaises(SkillMarketplaceError):
                publish_skill(
                    source_dir,
                    slug="../escape",
                    version="1.0.0",
                    hub_dir=root / "hub" / "marketplace",
                )

    def test_publish_with_external_manifest_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "sample-skill"
            source_dir.mkdir(parents=True, exist_ok=True)
            (source_dir / "SKILL.md").write_text("# sample", encoding="utf-8")
            manifest_path = root / "custom-manifest" / "manifest.local.json"

            result = publish_skill(
                source_dir,
                slug="sample-skill",
                version="1.2.3",
                hub_dir=root / "hub" / "marketplace",
                manifest_path=manifest_path,
                download_base_url="https://example.com/packages",
            )

            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["skills"][0]["slug"], "sample-skill")
            self.assertTrue(manifest["skills"][0]["package_file"].endswith(".zip"))

    def test_auto_update_strict_blocks_missing_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_dir = root / "installed"
            manifest_path = root / "installed.json"

            archive, checksum = self._make_skill_zip(root, "demo", "1.0.0", "# demo v1")
            index_v1 = self._write_index(
                root / "v1",
                {
                    "slug": "demo",
                    "version": "1.0.0",
                    "description": "demo",
                    "download_url": archive.as_uri(),
                    "checksum_sha256": checksum,
                },
            )
            install_skill(
                "demo",
                index_url=index_v1.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                allow_file_urls=True,
            )

            index_missing_checksum = self._write_index(
                root / "v2",
                {
                    "slug": "demo",
                    "version": "1.1.0",
                    "description": "demo",
                    "download_url": archive.as_uri(),
                    "checksum_sha256": "",
                },
            )

            result = update_skills(
                index_url=index_missing_checksum.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                allow_file_urls=True,
                strict=True,
            )
            self.assertEqual(len(result["updated"]), 0)
            self.assertEqual(result["blocked"][0]["slug"], "demo")

    def test_auto_update_dry_run_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_dir = root / "installed"
            manifest_path = root / "installed.json"

            archive_v1, checksum_v1 = self._make_skill_zip(root, "demo", "1.0.0", "# demo v1")
            index_v1 = self._write_index(
                root / "v1",
                {
                    "slug": "demo",
                    "version": "1.0.0",
                    "description": "demo",
                    "download_url": archive_v1.as_uri(),
                    "checksum_sha256": checksum_v1,
                },
            )
            install_skill(
                "demo",
                index_url=index_v1.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                allow_file_urls=True,
            )

            archive_v2, checksum_v2 = self._make_skill_zip(root, "demo", "1.1.0", "# demo v2")
            index_v2 = self._write_index(
                root / "v2",
                {
                    "slug": "demo",
                    "version": "1.1.0",
                    "description": "demo",
                    "download_url": archive_v2.as_uri(),
                    "checksum_sha256": checksum_v2,
                },
            )

            preview = update_skills(
                index_url=index_v2.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                dry_run=True,
                allow_file_urls=True,
            )
            self.assertTrue(preview["updated"][0]["dry_run"])
            self.assertIn("v1", (install_dir / "demo" / "SKILL.md").read_text(encoding="utf-8"))

            applied = update_skills(
                index_url=index_v2.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                dry_run=False,
                allow_file_urls=True,
            )
            self.assertEqual(applied["updated"][0]["version"], "1.1.0")
            self.assertIn("v2", (install_dir / "demo" / "SKILL.md").read_text(encoding="utf-8"))

    def test_auto_update_rollback_on_failed_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_dir = root / "installed"
            manifest_path = root / "installed.json"

            archive_v1, checksum_v1 = self._make_skill_zip(root, "demo", "1.0.0", "# demo v1")
            index_v1 = self._write_index(
                root / "v1",
                {
                    "slug": "demo",
                    "version": "1.0.0",
                    "description": "demo",
                    "download_url": archive_v1.as_uri(),
                    "checksum_sha256": checksum_v1,
                },
            )
            install_skill(
                "demo",
                index_url=index_v1.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                allow_file_urls=True,
            )

            bad_zip = root / "demo-1.1.0.zip"
            with zipfile.ZipFile(bad_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("README.txt", "invalid package")
            bad_checksum = hashlib.sha256(bad_zip.read_bytes()).hexdigest()
            bad_index = self._write_index(
                root / "v2",
                {
                    "slug": "demo",
                    "version": "1.1.0",
                    "description": "demo",
                    "download_url": bad_zip.as_uri(),
                    "checksum_sha256": bad_checksum,
                },
            )

            result = update_skills(
                index_url=bad_index.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                dry_run=False,
                allow_file_urls=True,
            )
            self.assertEqual(len(result["updated"]), 0)
            self.assertEqual(result["blocked"][0]["slug"], "demo")
            self.assertIn("v1", (install_dir / "demo" / "SKILL.md").read_text(encoding="utf-8"))
            installed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(installed_manifest["skills"]["demo"]["version"], "1.0.0")

    def test_runtime_auto_update_payload_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_dir = root / "installed"
            manifest_path = root / "installed.json"

            archive, checksum = self._make_skill_zip(root, "demo", "1.0.0", "# demo v1")
            index = self._write_index(
                root,
                {
                    "slug": "demo",
                    "version": "1.0.0",
                    "description": "demo",
                    "download_url": archive.as_uri(),
                    "checksum_sha256": checksum,
                },
            )
            install_skill(
                "demo",
                index_url=index.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                allow_file_urls=True,
            )

            payload = build_auto_update_runtime_payload(
                index_url=index.as_uri(),
                strict=False,
                allow_hosts=[],
                manifest_path=str(manifest_path),
                install_dir=str(install_dir),
                allow_file_urls=True,
            )
            result = run_runtime_auto_update(payload)
            self.assertEqual(result["skipped"][0]["reason"], "up-to-date")

            job_id = schedule_auto_update(
                every_seconds=60,
                index_url=index.as_uri(),
                strict=False,
                allow_hosts=[],
                manifest_path=str(manifest_path),
                install_dir=str(install_dir),
                allow_file_urls=True,
            )
            self.assertGreater(job_id, 0)


if __name__ == "__main__":
    unittest.main()
