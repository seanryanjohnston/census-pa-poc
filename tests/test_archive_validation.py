from pathlib import Path

import pandas as pd

from census_pa_poc.archive_validation import (
    archive_path_failures,
    retained_path_failures,
    selector_mapping_precinct_hits,
    stale_original_failures,
)


def test_archive_manifest_paths_and_active_selectors() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = pd.read_csv(
        root / "mappings/poc030_archive_manifest_v1.csv",
        dtype="string",
        keep_default_na=False,
    )
    tracked_archive = manifest[
        ~manifest["category"].isin(["generated_data", "proof_artifacts"])
    ]
    assert not archive_path_failures(root, tracked_archive)
    assert not stale_original_failures(root, manifest)
    assert not retained_path_failures(root, manifest)
    assert not selector_mapping_precinct_hits(root)
