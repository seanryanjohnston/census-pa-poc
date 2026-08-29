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
    return _load_pl94_block_population(archive, county_fips)


def load_pl94_block_population_statewide(archive: Path) -> pd.DataFrame:
    """Read 2020 PL 94-171 block total population for all Pennsylvania blocks."""
    return _load_pl94_block_population(archive, None)


def load_2010_pl94_block_population(archive: Path) -> pd.DataFrame:
    """Read Pennsylvania 2010 PL 94-171 block total population.

    The 2010 geographic header is fixed-width while File 01 is comma-delimited.
    Offsets follow the official 2010 PL technical documentation: ``SUMLEV`` at
    position 9, ``LOGRECNO`` at 19, ``STATE`` at 28, ``COUNTY`` at 30,
    ``TRACT`` at 55, and ``BLOCK`` at 62 (all one-based positions).
    """
    with ZipFile(archive) as zf:
        geography = {}
        with zf.open("pageo2010.pl") as source:
            for raw_line in source:
                line = raw_line.decode("latin-1")
                if line[8:11] != "750" or line[27:29] != "42":
                    continue
                geography[line[18:25]] = (
                    line[27:29] + line[29:32] + line[54:60] + line[61:65]
                )

        populations = {}
        with zf.open("pa000012010.pl") as source:
            for raw_line in source:
                row = next(
                    csv.reader([raw_line.decode("latin-1").rstrip("\r\n")])
                )
                if row[4] in geography:
                    populations[row[4]] = int(row[5])

    rows = [
        {"source_block_geoid": geoid, "P0010001": populations.get(logrecno)}
        for logrecno, geoid in geography.items()
    ]
    return pd.DataFrame(rows).sort_values("source_block_geoid").reset_index(drop=True)


def load_2010_census_blocks(archive: Path) -> gpd.GeoDataFrame:
    """Load statewide 2010 Pennsylvania tabulation block geometry."""
    return gpd.read_file(
        vsi_zip_member(archive, "tl_2010_42_tabblock10.shp"),
        columns=[
            "STATEFP10",
            "COUNTYFP10",
            "TRACTCE10",
            "BLOCKCE10",
            "GEOID10",
            "ALAND10",
            "AWATER10",
            "INTPTLAT10",
            "INTPTLON10",
        ],
    )


def load_2010_2020_block_relationship(archive: Path) -> pd.DataFrame:
    """Load official 2010-to-2020 block relationships originating in PA."""
    frame = pd.read_csv(
        archive,
        sep="|",
        dtype="string",
        encoding="utf-8-sig",
    )
    frame = frame[frame["STATE_2010"].eq("42")].copy()
    frame["source_block_geoid"] = (
        frame["STATE_2010"]
        + frame["COUNTY_2010"]
        + frame["TRACT_2010"]
        + frame["BLK_2010"]
    )
    frame["target_2020_block_geoid"] = (
        frame["STATE_2020"]
        + frame["COUNTY_2020"]
        + frame["TRACT_2020"]
        + frame["BLK_2020"]
    )
    for column in [
        "AREALAND_2010",
        "AREAWATER_2010",
        "AREALAND_INT",
        "AREAWATER_INT",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype("int64")
    return frame.sort_values(
        ["source_block_geoid", "target_2020_block_geoid"], kind="stable"
    ).reset_index(drop=True)


def _load_pl94_block_population(archive: Path, county_fips: str | None) -> pd.DataFrame:
    with ZipFile(archive) as zf:
        geography = {
            row[7]: row[9]
            for row in _pipe_rows(zf, "pageo2020.pl")
            if row[2] == "750"
            and row[12] == "42"
            and (county_fips is None or row[14] == county_fips)
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
