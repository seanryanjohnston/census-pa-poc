"""Load the exact source products used by the Cumberland proof."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd

CUMBERLAND_COUNTY_FIPS = "041"
PHILADELPHIA_COUNTY_FIPS = "101"


def sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def vsi_zip_member(archive: Path, member: str) -> str:
    """Build a GDAL virtual-file path for one member of a ZIP archive."""
    return f"/vsizip/{archive.resolve()}/{member}"


def load_census_blocks(archive: Path, county_fips: str) -> gpd.GeoDataFrame:
    """Load Census 2020 tabulation blocks for one Pennsylvania county."""
    return gpd.read_file(
        vsi_zip_member(archive, "tl_2020_42_tabblock20.shp"),
        where=f"COUNTYFP20 = '{county_fips}'",
        columns=[
            "STATEFP20",
            "COUNTYFP20",
            "TRACTCE20",
            "BLOCKCE20",
            "GEOID20",
            "ALAND20",
            "AWATER20",
            "INTPTLAT20",
            "INTPTLON20",
        ],
    )


def load_lrc_blocks(archive: Path, county_fips: str) -> gpd.GeoDataFrame:
    """Load LRC Release 1b blocks and their published precinct fields."""
    return gpd.read_file(
        vsi_zip_member(archive, "Geography/WP_Blocks.shp"),
        where=f"COUNTYFP20 = '{county_fips}'",
        columns=[
            "FIPS",
            "VTD",
            "P0010001",
            "STATEFP20",
            "COUNTYFP20",
            "VTDST20",
            "GEOID20",
            "VTD_NAME",
        ],
    )


def load_lrc_precincts(archive: Path, county_fips: str) -> gpd.GeoDataFrame:
    """Load LRC Release 1b voting districts for one county."""
    return gpd.read_file(
        vsi_zip_member(archive, "Geography/WP_VotingDistricts.shp"),
        where=f"COUNTYFP20 = '{county_fips}'",
        columns=[
            "FIPS",
            "VTD",
            "NAME",
            "P0010001",
            "STATEFP20",
            "COUNTYFP20",
            "VTDST20",
            "GEOID20",
        ],
    )


def load_philadelphia_divisions(path: Path) -> gpd.GeoDataFrame:
    """Load the frozen City of Philadelphia political-division snapshot."""
    return gpd.read_file(
        path,
        columns=["objectid", "short_div_num", "division_num"],
    )


def _pipe_rows(zf: ZipFile, member: str) -> Iterator[list[str]]:
    with zf.open(member) as source:
        for raw_line in source:
            line = raw_line.decode("utf-8").rstrip("\r\n")
            yield next(csv.reader([line], delimiter="|"))


def load_pl94_block_population(archive: Path, county_fips: str) -> pd.DataFrame:
    """Read 2020 PL 94-171 block total population for one county.

    The legacy state file has no header. Field positions follow the official
    2020 PL 94-171 state summary-file layout: ``SUMLEV`` 2, ``LOGRECNO`` 7,
    ``GEOCODE`` 9, ``STATE`` 12, and ``COUNTY`` 14 in the geography file;
    ``LOGRECNO`` 4 and ``P0010001`` 5 in File 01.
    """
    with ZipFile(archive) as zf:
        geography = {
            row[7]: row[9]
            for row in _pipe_rows(zf, "pageo2020.pl")
            if row[2] == "750" and row[12] == "42" and row[14] == county_fips
        }
        populations = {
            row[4]: int(row[5])
            for row in _pipe_rows(zf, "pa000012020.pl")
            if row[4] in geography
        }

    rows = [
        {"source_block_geoid": geocode, "P0010001": populations.get(logrecno)}
        for logrecno, geocode in geography.items()
    ]
    return pd.DataFrame(rows).sort_values("source_block_geoid").reset_index(drop=True)
