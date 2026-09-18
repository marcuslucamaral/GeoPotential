"""Level 3 — the QA/QC rules against the deliberately defective datasets.

This is gate M3's G1 and G2. Every fixture in `MANIFEST.json` declares the rule
and the severity it must produce; the manifest is the assertion, not a
description of whatever the code happens to do. A mismatch is a failing gate,
not a fixture to adjust.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from geopotential_worker.io.describe import describe
from geopotential_worker.qc import Severity, validate

ROOT = Path(__file__).resolve().parents[2]


def _data_dir() -> Path:
    """`data/` inside the tree when there is one, beside it otherwise.

    Both layouts are legitimate: the development workspace keeps the datasets
    as a sibling, and a clone of the repository carries them inside. See
    `tools/datadir.py`.
    """
    import os

    declared = os.environ.get("GEOPOTENTIAL_DATA")
    if declared:
        return Path(declared).expanduser().resolve()
    inside = ROOT / "data"
    return inside if inside.is_dir() else (ROOT.parent / "data").resolve()


_DATA = _data_dir()
BROKEN = _DATA / "synthetic" / "msp" / "broken"
MANIFEST = BROKEN / "MANIFEST.json"
CLEAN = _DATA / "utah_forge" / "Distance_to_fault.tif"


def fixtures() -> list[dict]:
    if not MANIFEST.exists():
        return []
    return json.loads(MANIFEST.read_text())["fixtures"]


@unittest.skipUnless(MANIFEST.exists(),
                     "run tools/make_broken_fixtures.py first")
class EachDefectIsDetected(unittest.TestCase):
    """G1: detect errors — the right one, not merely some error."""

    def test_every_fixture_produces_its_declared_rule(self) -> None:
        for entry in fixtures():
            with self.subTest(fixture=entry["file"]):
                report = self._validate(entry)
                rules_found = {f.rule for f in report.findings}
                self.assertIn(
                    entry["expected_rule"], rules_found,
                    f"{entry['file']} ({entry['defect']}) should raise "
                    f"{entry['expected_rule']}; got {sorted(rules_found)}",
                )

    def test_every_fixture_produces_its_declared_severity(self) -> None:
        for entry in fixtures():
            with self.subTest(fixture=entry["file"]):
                report = self._validate(entry)
                matching = [
                    f for f in report.findings if f.rule == entry["expected_rule"]
                ]
                self.assertTrue(matching, f"{entry['expected_rule']} not raised")
                self.assertEqual(
                    matching[0].severity.value, entry["expected_severity"],
                    f"{entry['file']}: severity is a scientific decision and "
                    f"changing it belongs in docs/decisions/",
                )

    def test_a_blocker_makes_the_dataset_unusable(self) -> None:
        """G4: a BLOCKER blocks. It is not a redder warning."""
        for entry in fixtures():
            if entry["expected_severity"] != "BLOCKER":
                continue
            with self.subTest(fixture=entry["file"]):
                report = self._validate(entry)
                self.assertFalse(
                    report.usable,
                    f"{entry['file']} has a blocking defect and must be refused",
                )

    def test_a_warning_does_not_block(self) -> None:
        """A warning that blocked would make the two levels the same level."""
        for entry in fixtures():
            if entry["expected_severity"] != "WARNING":
                continue
            with self.subTest(fixture=entry["file"]):
                report = self._validate(entry)
                offending = [f.rule for f in report.blockers]
                self.assertFalse(
                    offending,
                    f"{entry['file']} should warn, not block; blockers: {offending}",
                )

    @staticmethod
    def _validate(entry: dict):
        path = BROKEN / entry["file"]
        # Two fixtures only misbehave in a context: a disjoint extent needs
        # other layers to be disjoint from, and a geographic CRS is only wrong
        # when the operation measures in metres.
        context = []
        if entry["expected_rule"] in ("extent.overlap", "grid.resolution_mismatch"):
            context = [{
                "name": "Distance_to_fault.tif",
                "extent": [330894.4, 4259645.2, 340684.4, 4267855.2],
                "pixel_size": [10.0, 10.0],
            }]
        return validate(
            describe(path),
            context=context,
            require_metric=entry["expected_rule"] == "crs.metric_required",
        )


@unittest.skipUnless(MANIFEST.exists(), "fixtures absent")
class MessagesAreActionable(unittest.TestCase):
    """G2: explain errors. MSP-04 forbids reducing QA/QC to a generic warning."""

    def test_every_finding_is_actionable(self) -> None:
        for entry in fixtures():
            report = EachDefectIsDetected._validate(entry)
            for finding in report.findings:
                with self.subTest(fixture=entry["file"], rule=finding.rule):
                    self.assertTrue(
                        finding.is_actionable,
                        f"{finding.rule}: {finding.message!r} is not actionable",
                    )

    def test_every_finding_names_the_dataset(self) -> None:
        for entry in fixtures():
            report = EachDefectIsDetected._validate(entry)
            for finding in report.findings:
                with self.subTest(fixture=entry["file"], rule=finding.rule):
                    self.assertIn(entry["file"], finding.message)

    def test_every_finding_answers_section_33(self) -> None:
        """what failed, why it matters, and what to correct — all three."""
        for entry in fixtures():
            report = EachDefectIsDetected._validate(entry)
            for finding in report.findings:
                with self.subTest(fixture=entry["file"], rule=finding.rule):
                    self.assertTrue(finding.what.strip(), "no 'what'")
                    self.assertTrue(finding.why.strip(), "no 'why'")
                    self.assertTrue(finding.fix.strip(), "no 'fix'")
                    self.assertGreater(
                        len(finding.fix), 20,
                        f"{finding.rule}: the fix is too short to be advice",
                    )

    def test_the_summary_states_the_verdict(self) -> None:
        for entry in fixtures():
            report = EachDefectIsDetected._validate(entry)
            summary = report.summary()
            self.assertIn(entry["file"], summary)
            if entry["expected_severity"] == "BLOCKER":
                self.assertIn("cannot be used", summary)


class TheRefusalStaysWhereTheDamageIs(unittest.TestCase):
    """ADR-MSP-005 moved a warning; it must not have moved the protection.

    A disjoint layer is importable. What it may never do is produce an empty
    analysis grid quietly — harmonization refuses it, by name.
    """

    @unittest.skipUnless((BROKEN / "disjoint.tif").exists()
                         and CLEAN.exists(), "fixtures absent")
    def test_harmonization_still_refuses_an_empty_intersection(self) -> None:
        from geopotential_worker.domain.crs import CrsInfo
        from geopotential_worker.grid.harmonize import (
            ExtentPolicy, build_target_grid,
        )
        from geopotential_worker.io.readers import read_raster

        near = read_raster(CLEAN)
        far = read_raster(BROKEN / "disjoint.tif")
        with self.assertRaises(ValueError) as refusal:
            build_target_grid(
                [near, far],
                CrsInfo.from_user_input("EPSG:26912", source="test"),
                (10.0, 10.0), policy=ExtentPolicy.INTERSECTION,
            )
        message = str(refusal.exception)
        self.assertIn("CRS", message)
        self.assertIn("empty", message)


@unittest.skipUnless(CLEAN.exists(), "the smoke dataset is absent")
class CleanDataPasses(unittest.TestCase):
    """The rules have to be quiet on good data, or they are noise."""

    def test_the_real_dataset_is_usable(self) -> None:
        report = validate(describe(CLEAN, overrides={"unit": "m"}))
        self.assertTrue(
            report.usable,
            f"the smoke dataset must pass; blockers: "
            f"{[f.message for f in report.blockers]}",
        )

    def test_the_real_dataset_raises_no_blocker(self) -> None:
        report = validate(describe(CLEAN, overrides={"unit": "m"}))
        self.assertEqual([f.rule for f in report.blockers], [])

    def test_describing_creates_nothing(self) -> None:
        """Describing is not importing. Section 9.2 depends on it."""
        before = {p.name for p in CLEAN.parent.iterdir()}
        describe(CLEAN)
        after = {p.name for p in CLEAN.parent.iterdir()}
        self.assertEqual(before, after)


@unittest.skipUnless(MANIFEST.exists(), "fixtures absent")
class CorrectionIsPossible(unittest.TestCase):
    """G3: permit correction. A declared value makes a refused file usable."""

    def test_declaring_a_crs_clears_the_blocker(self) -> None:
        path = BROKEN / "no_crs.tif"
        before = validate(describe(path))
        self.assertFalse(before.usable)
        self.assertIn("crs.present", {f.rule for f in before.blockers})

        after = validate(describe(path, overrides={"crs": "EPSG:26912", "unit": "m"}))
        self.assertNotIn("crs.present", {f.rule for f in after.findings})
        self.assertTrue(after.usable, [f.message for f in after.blockers])

    def test_declaring_nodata_clears_the_blocker(self) -> None:
        path = BROKEN / "nodata_undeclared.tif"
        before = validate(describe(path))
        self.assertIn("nodata.declared", {f.rule for f in before.blockers})

        after = validate(describe(path, overrides={"nodata": -9999.0, "unit": "m"}))
        self.assertNotIn("nodata.declared", {f.rule for f in after.findings})
        self.assertTrue(after.usable, [f.message for f in after.blockers])

    def test_declaring_a_source_crs_clears_a_table(self) -> None:
        path = BROKEN / "no_source_crs.csv"
        before = validate(describe(path))
        self.assertFalse(before.usable)

        after = validate(describe(path, overrides={"crs": "EPSG:26912"}))
        self.assertNotIn("crs.present", {f.rule for f in after.findings})

    def test_correcting_a_unit_clears_the_plausibility_warning(self) -> None:
        path = BROKEN / "wrong_unit.csv"
        before = validate(describe(path))
        self.assertIn("unit.plausible", {f.rule for f in before.findings})

        after = validate(describe(path, overrides={"unit": "mGal"}))
        self.assertNotIn("unit.plausible", {f.rule for f in after.findings})


if __name__ == "__main__":
    unittest.main()
