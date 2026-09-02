"""Load the exact source products used by the Cumberland proof."""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import LineString, Point

CUMBERLAND_COUNTY_FIPS = "041"
PHILADELPHIA_COUNTY_FIPS = "101"


class PublishedPopulationTotalsUnavailableError(ValueError):
    """The accepted local Census extract omits direct state/county rows."""


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


def load_pl94_block_vap_statewide(archive: Path) -> pd.DataFrame:
    """Read 2020 PL 94-171 block voting-age population for Pennsylvania.

    ``P0030001`` is the total of table P3, whose universe is the population
    18 years and over. In the legacy state summary file it is the first table
    cell in File 02, after the five file-identification fields.
    """
    return _load_pl94_block_metric(
        archive,
        member="pa000022020.pl",
        metric_id="P0030001",
    )


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
                row = next(csv.reader([raw_line.decode("latin-1").rstrip("\r\n")]))
                if row[4] in geography:
                    populations[row[4]] = int(row[5])

    rows = [
        {"source_block_geoid": geoid, "P0010001": populations.get(logrecno)}
        for logrecno, geoid in geography.items()
    ]
    return pd.DataFrame(rows).sort_values("source_block_geoid").reset_index(drop=True)


def load_2000_pl94_block_population(
    geography_archive: Path, file01_archive: Path
) -> pd.DataFrame:
    """Read Pennsylvania Census 2000 PL 94-171 block total population.

    The geography and File 01 products are separate archives. The geographic
    header offsets follow the Census 2000 state summary file: ``SUMLEV`` at
    position 9, ``LOGRECNO`` at 19, ``STATE`` at 30, ``COUNTY`` at 32,
    ``TRACT`` at 56, and ``BLOCK`` at 63 (one-based).
    File 01 is comma-delimited and its first table cell is PL1 total population.
    """
    with ZipFile(geography_archive) as zf:
        geography = {}
        with zf.open("pageo.upl") as source:
            for raw_line in source:
                line = raw_line.decode("latin-1")
                if line[8:11] != "750" or line[29:31] != "42":
                    continue
                geography[line[18:25]] = (
                    line[29:31] + line[31:34] + line[55:61] + line[62:66]
                )

    with ZipFile(file01_archive) as zf:
        populations = {}
        with zf.open("pa00001.upl") as source:
            for raw_line in source:
                row = next(csv.reader([raw_line.decode("latin-1").rstrip("\r\n")]))
                if row[4] in geography:
                    populations[row[4]] = int(row[5])

    rows = [
        {"source_block_geoid": geoid, "P0010001": populations.get(logrecno)}
        for logrecno, geoid in geography.items()
    ]
    return pd.DataFrame(rows).sort_values("source_block_geoid").reset_index(drop=True)


def load_2000_census_blocks(archive: Path) -> gpd.GeoDataFrame:
    """Load statewide Census 2000 Pennsylvania tabulation block geometry."""
    return gpd.read_file(
        vsi_zip_member(archive, "tl_2010_42_tabblock00.shp"),
        columns=[
            "STATEFP00",
            "COUNTYFP00",
            "TRACTCE00",
            "BLOCKCE00",
            "BLKIDFP00",
            "ALAND00",
            "AWATER00",
            "INTPTLAT00",
            "INTPTLON00",
        ],
    )


def load_2000_2010_block_relationship(archive: Path) -> pd.DataFrame:
    """Load official 2000-to-2010 block relationships originating in PA."""
    frame = pd.read_csv(
        archive,
        sep=",",
        dtype="string",
        encoding="utf-8-sig",
        skipinitialspace=True,
    )
    frame.columns = frame.columns.str.strip()
    frame = frame[frame["STATE_2000"].str.strip().eq("42")].copy()
    for column in frame.columns:
        if frame[column].dtype.name == "string":
            frame[column] = frame[column].str.strip()
    frame["source_block_geoid"] = (
        frame["STATE_2000"]
        + frame["COUNTY_2000"]
        + frame["TRACT_2000"]
        + frame["BLK_2000"]
    )
    frame["target_2010_block_geoid"] = (
        frame["STATE_2010"]
        + frame["COUNTY_2010"]
        + frame["TRACT_2010"]
        + frame["BLK_2010"]
    )
    for column in [
        "AREALAND_2000",
        "AREAWATER_2000",
        "AREALAND_INT",
        "AREAWATER_INT",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype("int64")
    return frame.sort_values(
        ["source_block_geoid", "target_2010_block_geoid"], kind="stable"
    ).reset_index(drop=True)


def load_acs5_2015_block_group_population(
    geography_path: Path,
    sequence_archive: Path,
) -> pd.DataFrame:
    """Load 2011–2015 ACS B01003 estimate/MOE rows for Pennsylvania block groups."""
    geography = _load_acs5_block_group_geography(geography_path)
    with ZipFile(sequence_archive) as zf:
        estimates = _load_acs5_sequence_cell(zf, "e20155pa0003000.txt", 129)
        margins = _load_acs5_sequence_cell(zf, "m20155pa0003000.txt", 129)

    result = geography.copy()
    result["B01003_001E"] = result["LOGRECNO"].map(estimates)
    result["B01003_001M"] = result["LOGRECNO"].map(margins)
    for column in ["B01003_001E", "B01003_001M"]:
        result[column] = pd.to_numeric(result[column], errors="raise").astype("int64")
    return result.sort_values("source_block_group_geoid").reset_index(drop=True)


def load_acs5_block_group_population(year: int, directory: Path) -> pd.DataFrame:
    """Load Pennsylvania B01003 estimate/MOE rows for one ACS five-year product.

    Products through 2020 use the official sequence-based Summary File. Products
    from 2021 onward use the official table-based B01003 file. The 2009
    geography header is fixed-width; subsequent sequence products use CSV.
    """
    if 2009 <= year <= 2020:
        return _load_sequence_acs5_block_group_population(year, directory)
    if 2021 <= year <= 2024:
        return _load_table_acs5_block_group_population(year, directory)
    raise ValueError(f"Unsupported ACS five-year estimate year: {year}")


def load_acs5_published_population_totals(year: int, directory: Path) -> pd.DataFrame:
    """Load directly published Pennsylvania state/county B01003 totals.

    This is deliberately separate from :func:`load_acs5_block_group_population`:
    the returned rows are independent published aggregates, not sums computed
    from the block-group rows used by the POC allocation. Census uses a negative
    sentinel for the controlled total-population MOE; that sentinel is converted
    to a typed missing value rather than exposed as a real margin of error.
    """
    if 2009 <= year <= 2020:
        return _load_sequence_acs5_published_population_totals(year, directory)
    if 2021 <= year <= 2024:
        return _load_table_acs5_published_population_totals(year, directory)
    raise ValueError(f"Unsupported ACS five-year estimate year: {year}")


def _load_sequence_acs5_published_population_totals(
    year: int, directory: Path
) -> pd.DataFrame:
    lookup = _load_acs5_sequence_lookup(directory / "sequence_lookup.txt")
    sequence = str(lookup["sequence_number"]).zfill(4)
    position = int(lookup["start_position"])
    geography_suffix = "txt" if year == 2009 else "csv"
    geography_path = directory / f"g{year}5pa.{geography_suffix}"
    archive_path = directory / f"{year}5pa{sequence}000.zip"
    geography = _load_acs5_published_geography(year, geography_path)
    with ZipFile(archive_path) as zf:
        estimates = _load_acs5_sequence_cell(
            zf, f"e{year}5pa{sequence}000.txt", position - 1
        )
        margins = _load_acs5_sequence_cell(
            zf, f"m{year}5pa{sequence}000.txt", position - 1
        )
    result = geography.copy()
    result["published_estimate"] = result["LOGRECNO"].map(estimates)
    result["published_margin_of_error"] = result["LOGRECNO"].map(margins)
    if result["published_estimate"].isna().all():
        raise PublishedPopulationTotalsUnavailableError(
            f"{year} accepted Summary File archive contains tract/block-group "
            "records but no state/county B01003 cells"
        )
    return _normalize_acs5_published_population_totals(result)


def _load_acs5_published_geography(year: int, path: Path) -> pd.DataFrame:
    if year == 2009:
        return _load_acs5_2009_published_geography(path)
    rows = []
    with path.open(newline="", encoding="latin1") as source:
        for row in csv.reader(source):
            if row[2] not in {"040", "050"} or row[9] != "42":
                continue
            is_state = row[2] == "040"
            rows.append(
                {
                    "LOGRECNO": row[4],
                    "geography_level": "state" if is_state else "county",
                    "geography_id": "42" if is_state else row[10],
                    "geography_name": row[49],
                    "source_record_geoid": row[48],
                }
            )
    return pd.DataFrame(rows)


def _load_acs5_2009_published_geography(path: Path) -> pd.DataFrame:
    rows = []
    with path.open(encoding="latin1") as source:
        for line in source:
            summary_level = line[8:11]
            state = line[25:27]
            if summary_level not in {"040", "050"} or state != "42":
                continue
            is_state = summary_level == "040"
            county = line[27:30]
            rows.append(
                {
                    "LOGRECNO": line[13:20],
                    "geography_level": "state" if is_state else "county",
                    "geography_id": "42" if is_state else county,
                    "geography_name": line[230:].rstrip("\r\n").strip(),
                    "source_record_geoid": "0400000US42"
                    if is_state
                    else f"0500000US42{county}",
                }
            )
    return pd.DataFrame(rows)


def _load_table_acs5_published_population_totals(
    year: int, directory: Path
) -> pd.DataFrame:
    path = directory / f"acsdt5y{year}-b01003.dat"
    table = pd.read_csv(path, sep="|", dtype="string", keep_default_na=False)
    state = table[table["GEO_ID"].eq("0400000US42")].copy()
    state["geography_level"] = "state"
    state["geography_id"] = "42"
    counties = table[table["GEO_ID"].str.startswith("0500000US42")].copy()
    counties["geography_level"] = "county"
    counties["geography_id"] = counties["GEO_ID"].str.slice(-3)
    result = pd.concat([state, counties], ignore_index=True)
    result = result.rename(
        columns={
            "GEO_ID": "source_record_geoid",
            "NAME": "geography_name",
            "B01003_E001": "published_estimate",
            "B01003_M001": "published_margin_of_error",
        }
    )
    if "geography_name" not in result:
        result["geography_name"] = pd.NA
    return _normalize_acs5_published_population_totals(
        result[
            [
                "geography_level",
                "geography_id",
                "geography_name",
                "source_record_geoid",
                "published_estimate",
                "published_margin_of_error",
            ]
        ]
    )


def _normalize_acs5_published_population_totals(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        raise ValueError("No Pennsylvania ACS state/county B01003 rows found")
    result["geography_level"] = result["geography_level"].astype("string")
    result["geography_id"] = result["geography_id"].astype("string")
    result["geography_name"] = result["geography_name"].astype("string")
    result["source_record_geoid"] = result["source_record_geoid"].astype("string")
    result["published_estimate"] = pd.to_numeric(
        result["published_estimate"], errors="raise"
    ).astype("int64")
    raw_moe = pd.to_numeric(result["published_margin_of_error"], errors="raise")
    result["margin_of_error_status"] = raw_moe.ge(0).map(
        {
            True: "available",
            False: "controlled_estimate_no_meaningful_moe",
        }
    )
    result["published_margin_of_error"] = raw_moe.where(raw_moe.ge(0)).astype("Float64")
    if result[["geography_level", "geography_id"]].duplicated().any():
        raise ValueError("Duplicate ACS state/county B01003 identifiers")
    if result["published_estimate"].lt(0).any():
        raise ValueError("Negative ACS state/county B01003 estimate")
    return result.sort_values(
        ["geography_level", "geography_id"], kind="stable"
    ).reset_index(drop=True)


def _load_sequence_acs5_block_group_population(
    year: int, directory: Path
) -> pd.DataFrame:
    lookup = _load_acs5_sequence_lookup(directory / "sequence_lookup.txt")
    sequence = str(lookup["sequence_number"]).zfill(4)
    position = int(lookup["start_position"])
    geography_suffix = "txt" if year == 2009 else "csv"
    geography_path = directory / f"g{year}5pa.{geography_suffix}"
    archive_path = directory / f"{year}5pa{sequence}000.zip"
    geography = _load_acs5_block_group_geography_for_year(year, geography_path)
    with ZipFile(archive_path) as zf:
        estimates = _load_acs5_sequence_cell(
            zf, f"e{year}5pa{sequence}000.txt", position - 1
        )
        margins = _load_acs5_sequence_cell(
            zf, f"m{year}5pa{sequence}000.txt", position - 1
        )
    result = geography.copy()
    result["B01003_001E"] = result["LOGRECNO"].map(estimates)
    result["B01003_001M"] = result["LOGRECNO"].map(margins)
    return _normalize_acs5_population(result)


def _load_acs5_sequence_lookup(path: Path) -> dict[str, int]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        position = row.get("Start Position") or row.get("position") or ""
        if row.get("Table ID") != "B01003" or position.strip() in {"", "."}:
            continue
        sequence = row.get("Sequence Number") or row.get("seq")
        return {
            "sequence_number": int(str(sequence)),
            "start_position": int(position),
        }
    raise ValueError(f"B01003 sequence position not found in {path}")


def _load_acs5_block_group_geography_for_year(year: int, path: Path) -> pd.DataFrame:
    if year == 2009:
        return _load_acs5_2009_block_group_geography(path)
    return _load_acs5_block_group_geography(path)


def _load_acs5_2009_block_group_geography(path: Path) -> pd.DataFrame:
    rows = []
    with path.open(encoding="latin1") as source:
        for line in source:
            if line[8:11] != "150":
                continue
            rows.append(
                {
                    "LOGRECNO": line[13:20],
                    "source_block_group_geoid": (
                        line[25:27] + line[27:30] + line[40:46] + line[46:47]
                    ),
                    "NAME": line[230:].rstrip("\r\n"),
                }
            )
    return pd.DataFrame(rows)


def _load_table_acs5_block_group_population(year: int, directory: Path) -> pd.DataFrame:
    path = directory / f"acsdt5y{year}-b01003.dat"
    table = pd.read_csv(path, sep="|", dtype="string", keep_default_na=False)
    block_groups = table[table["GEO_ID"].str.startswith("1500000US42")].copy()
    block_groups["source_block_group_geoid"] = block_groups["GEO_ID"].str.slice(9)
    block_groups = block_groups.rename(
        columns={"B01003_E001": "B01003_001E", "B01003_M001": "B01003_001M"}
    )
    return _normalize_acs5_population(
        block_groups[["source_block_group_geoid", "B01003_001E", "B01003_001M"]]
    )


def _normalize_acs5_population(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["source_block_group_geoid"] = result["source_block_group_geoid"].astype(
        "string"
    )
    for column in ["B01003_001E", "B01003_001M"]:
        result[column] = pd.to_numeric(result[column], errors="raise").astype("int64")
    if result["source_block_group_geoid"].duplicated().any():
        raise ValueError("Duplicate ACS block-group identifiers")
    if result[["B01003_001E", "B01003_001M"]].lt(0).any().any():
        raise ValueError("Negative ACS estimate or margin of error")
    return result.sort_values("source_block_group_geoid").reset_index(drop=True)


def _load_acs5_block_group_geography(path: Path) -> pd.DataFrame:
    rows = []
    with path.open(newline="", encoding="latin1") as source:
        for row in csv.reader(source):
            if row[2] != "150":
                continue
            rows.append(
                {
                    "LOGRECNO": row[4],
                    "source_block_group_geoid": row[9] + row[10] + row[13] + row[14],
                    "NAME": row[49],
                }
            )
    return pd.DataFrame(rows)


def _load_acs5_sequence_cell(
    archive: ZipFile,
    member: str,
    zero_based_cell_index: int,
) -> dict[str, str]:
    result = {}
    with archive.open(member) as source:
        for raw_line in source:
            row = next(csv.reader([raw_line.decode("latin1")]))
            result[row[5]] = row[zero_based_cell_index]
    return result


def load_2015_census_block_groups(archive: Path) -> gpd.GeoDataFrame:
    """Load statewide 2015 TIGER/Line Pennsylvania block-group geometry."""
    return gpd.read_file(
        vsi_zip_member(archive, "tl_2015_42_bg.shp"),
        columns=[
            "STATEFP",
            "COUNTYFP",
            "TRACTCE",
            "BLKGRPCE",
            "GEOID",
            "NAMELSAD",
            "ALAND",
            "AWATER",
            "INTPTLAT",
            "INTPTLON",
        ],
    )


def load_1990_stf1b_block_population(archive: Path) -> pd.DataFrame:
    """Read every Pennsylvania block from the 1990 STF 1B header product.

    The associated geographic-header archive is sufficient for standard total
    population because its 300-character records carry ``POP100`` as well as
    the geographic identifiers. Summary level 100 is the block universe and
    includes zero-population/zero-housing blocks omitted from the full data
    file. Offsets follow the official machine-readable STF 1 dictionary.
    """
    rows = []
    with ZipFile(archive) as zf:
        members = zf.namelist()
        if len(members) != 1:
            raise ValueError(f"expected one STF 1B header member, found {members}")
        with zf.open(members[0]) as source:
            for raw_line in source:
                line = raw_line.decode("latin-1").rstrip("\r\n")
                if line[10:13] != "100" or line[132:134] != "42":
                    continue
                county = line[71:74]
                tract = _normalize_1990_tract(line[51:57])
                block = _normalize_1990_block(line[46:50])
                rows.append(
                    {
                        "source_block_geoid": f"42{county}{tract}{block}",
                        "P0010001": int(line[290:299]),
                        "HU100": int(line[259:268]),
                        "AREALAND_SQUARE_KILOMETERS": int(line[171:181]) / 1_000,
                        "AREAWATER_SQUARE_KILOMETERS": int(line[181:191]) / 1_000,
                        "INTPTLAT90": int(line[268:277]) / 1_000_000,
                        "INTPTLON90": int(line[277:287]) / 1_000_000,
                    }
                )
    return pd.DataFrame(rows).sort_values("source_block_geoid").reset_index(drop=True)


def load_1990_2000_block_relationship(directory: Path) -> pd.DataFrame:
    """Load the 67 official county-organized 1990-to-2000 block files.

    These files identify topological relationships and part flags only. They
    publish no area or population weights, so callers must not treat a row as
    an equal population share.
    """
    paths = sorted(directory.glob("t9t242*.txt"))
    if len(paths) != 67:
        raise ValueError(f"expected 67 relationship files, found {len(paths)}")
    columns = [
        "STATE_1990",
        "COUNTY_1990",
        "TRACT_1990",
        "BLOCK_1990",
        "BLOCK_PART_FLAG_1990",
        "STATE_2000",
        "COUNTY_2000",
        "TRACT_2000",
        "BLOCK_2000",
        "BLOCK_PART_FLAG_2000",
    ]
    frames = [
        pd.read_csv(
            path,
            header=None,
            names=columns,
            dtype="string",
            keep_default_na=False,
        )
        for path in paths
    ]
    frame = pd.concat(frames, ignore_index=True)
    frame["source_block_geoid"] = (
        frame["STATE_1990"].str.zfill(2)
        + frame["COUNTY_1990"].str.zfill(3)
        + frame["TRACT_1990"].map(_normalize_1990_tract)
        + frame["BLOCK_1990"].map(_normalize_1990_block)
    )
    frame["target_2000_block_geoid"] = (
        frame["STATE_2000"].str.zfill(2)
        + frame["COUNTY_2000"].str.zfill(3)
        + frame["TRACT_2000"].str.zfill(6)
        + frame["BLOCK_2000"].str.zfill(4)
    )
    return frame.sort_values(
        ["source_block_geoid", "target_2000_block_geoid"], kind="stable"
    ).reset_index(drop=True)


def load_1990_tiger_blocks(directory: Path) -> gpd.GeoDataFrame:
    """Reconstruct Pennsylvania 1990 blocks from Census 2000 TIGER topology.

    Census 2000 TIGER/Line Record Types 1 and 2 encode complete-chain
    coordinates; Record Type P provides one internal point for each resulting
    GT-polygon; and Record Type A supplies the 1990 block codes. The Census
    documentation states that this topology has a one-to-one relationship with
    the internal-point records. Raw GT-polygons are dissolved to tabulation
    block identifiers after reconstruction.
    """
    blocks, _ = load_1990_tiger_blocks_and_faces(directory)
    return blocks


def load_1990_tiger_blocks_and_faces(
    directory: Path,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Return dissolved 1990 blocks and same-topology 1990/2000 GT faces."""
    paths = sorted(directory.glob("tgr42*.zip"))
    if len(paths) != 67:
        raise ValueError(f"expected 67 TIGER archives, found {len(paths)}")
    county_faces = [_load_1990_2000_tiger_county_faces(path) for path in paths]
    faces = gpd.GeoDataFrame(
        pd.concat(county_faces, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4269",
    )
    counties = [_dissolve_1990_tiger_faces(frame) for frame in county_faces]
    combined = gpd.GeoDataFrame(
        pd.concat(counties, ignore_index=True), geometry="geometry", crs="EPSG:4269"
    )
    blocks = (
        combined.dissolve(
            by="source_block_geoid",
            as_index=False,
            aggfunc={
                "COUNTYFP90": "first",
                "TRACTCE90": "first",
                "BLOCKCE90": "first",
                "TIGER_INTERNAL_POINT_MATCH_COUNT": "max",
            },
        )
        .sort_values("source_block_geoid", kind="stable")
        .reset_index(drop=True)
    )
    return blocks, faces


def _load_1990_tiger_county_blocks(archive: Path) -> gpd.GeoDataFrame:
    return _dissolve_1990_tiger_faces(_load_1990_2000_tiger_county_faces(archive))


def _load_1990_2000_tiger_county_faces(archive: Path) -> gpd.GeoDataFrame:
    with ZipFile(archive) as zf:
        members = {Path(name).suffix.upper(): name for name in zf.namelist()}
        required = {".RT1", ".RT2", ".RTA", ".RTI", ".RTP", ".RTS"}
        missing = required - members.keys()
        if missing:
            raise ValueError(f"{archive.name} lacks TIGER members {sorted(missing)}")

        shape_points: dict[str, list[tuple[int, list[tuple[float, float]]]]] = (
            defaultdict(list)
        )
        with zf.open(members[".RT2"]) as source:
            for raw_line in source:
                line = raw_line.decode("ascii")
                points = []
                for index in range(10):
                    start = 18 + index * 19
                    longitude = line[start : start + 10]
                    latitude = line[start + 10 : start + 19]
                    if longitude == "+000000000" or latitude == "+00000000":
                        continue
                    points.append(_tiger_coordinate(longitude, latitude))
                shape_points[line[5:15].strip()].append((int(line[15:18]), points))

        chains = {}
        with zf.open(members[".RT1"]) as source:
            for raw_line in source:
                line = raw_line.decode("ascii")
                tlid = line[5:15].strip()
                points = [_tiger_coordinate(line[190:200], line[200:209])]
                for _, coordinates in sorted(shape_points.get(tlid, [])):
                    points.extend(coordinates)
                points.append(_tiger_coordinate(line[209:219], line[219:228]))
                chains[tlid] = LineString(points)

        faces = list(shapely.get_parts(shapely.polygonize(list(chains.values()))))
        face_tree = shapely.STRtree(faces)
        polygon_edges = defaultdict(list)
        with zf.open(members[".RTI"]) as source:
            for raw_line in source:
                line = raw_line.decode("ascii")
                chain = chains[line[5:15].strip()]
                for key in [
                    ("left", line[21:26].strip(), line[26:36].strip()),
                    ("right", line[36:41].strip(), line[41:51].strip()),
                ]:
                    side, cenid, polyid = key
                    if cenid and polyid:
                        polygon_edges[(cenid, polyid)].append((side, chain))
        internal_points = {}
        with zf.open(members[".RTP"]) as source:
            for raw_line in source:
                line = raw_line.decode("ascii")
                key = (line[10:15].strip(), line[15:25].strip())
                internal_points[key] = Point(
                    *_tiger_coordinate(line[25:35], line[35:44])
                )

        target_2000_blocks = {}
        with zf.open(members[".RTS"]) as source:
            for raw_line in source:
                line = raw_line.decode("ascii")
                key = (line[10:15].strip(), line[15:25].strip())
                state = line[46:48].strip()
                county = line[48:51].strip()
                tract = line[71:77].strip()
                block = line[77:81].strip()
                target_2000_blocks[key] = (
                    f"{state.zfill(2)}{county.zfill(3)}{tract.zfill(6)}{block.zfill(4)}"
                    if state and county and tract and block
                    else None
                )

        rows = []
        with zf.open(members[".RTA"]) as source:
            for raw_line in source:
                line = raw_line.decode("ascii")
                if line[89:91] != "42" or not line[46:50].strip():
                    continue
                key = (line[10:15].strip(), line[15:25].strip())
                matches = face_tree.query(internal_points[key], predicate="covered_by")
                if len(matches) == 0:
                    raise ValueError(
                        f"{archive.name} polygon {key} matched {len(matches)} faces"
                    )
                match = _select_tiger_face(faces, matches, polygon_edges[key])
                county = line[91:94]
                tract = _normalize_1990_tract(line[40:46])
                block = _normalize_1990_block(line[46:50])
                rows.append(
                    {
                        "source_block_geoid": f"42{county}{tract}{block}",
                        "COUNTYFP90": county,
                        "TRACTCE90": tract,
                        "BLOCKCE90": block,
                        "target_2000_block_geoid": target_2000_blocks[key],
                        "TIGER_INTERNAL_POINT_MATCH_COUNT": len(matches),
                        "geometry": faces[match],
                    }
                )

    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4269")


def _dissolve_1990_tiger_faces(raw: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return raw.dissolve(
        by="source_block_geoid",
        as_index=False,
        aggfunc={
            "COUNTYFP90": "first",
            "TRACTCE90": "first",
            "BLOCKCE90": "first",
            "TIGER_INTERNAL_POINT_MATCH_COUNT": "max",
        },
    )


def _normalize_1990_tract(value: str) -> str:
    return str(value).strip().ljust(6, "0")


def _normalize_1990_block(value: str) -> str:
    return str(value).strip().zfill(4)


def _tiger_coordinate(longitude: str, latitude: str) -> tuple[float, float]:
    return int(longitude) / 1_000_000, int(latitude) / 1_000_000


def _select_tiger_face(
    faces: list[object], matches: object, edges: list[tuple[str, LineString]]
) -> int:
    if len(matches) == 1:
        return int(matches[0])
    boundary = shapely.union_all([edge for _, edge in edges])
    overlap = [
        shapely.length(shapely.intersection(faces[int(index)].boundary, boundary))
        for index in matches
    ]
    maximum = max(overlap)
    winners = [index for index, value in enumerate(overlap) if value == maximum]
    if len(winners) == 1:
        return int(matches[winners[0]])

    closed = [(side, edge) for side, edge in edges if edge.is_ring]
    if len(closed) != 1:
        raise ValueError(f"ambiguous TIGER boundary overlap {overlap}")
    side, edge = closed[0]
    target_is_ring_interior = (side == "left") == shapely.is_ccw(
        shapely.LinearRing(edge.coords)
    )
    candidate_areas = [faces[int(matches[index])].area for index in winners]
    selected_area = (
        min(candidate_areas) if target_is_ring_interior else max(candidate_areas)
    )
    winner = winners[candidate_areas.index(selected_area)]
    return int(matches[winner])


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
    return _load_pl94_block_metric(
        archive,
        member="pa000012020.pl",
        metric_id="P0010001",
        county_fips=county_fips,
    )


def _load_pl94_block_metric(
    archive: Path,
    member: str,
    metric_id: str,
    county_fips: str | None = None,
) -> pd.DataFrame:
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
            for row in _pipe_rows(zf, member)
            if row[4] in geography
        }

    rows = [
        {"source_block_geoid": geocode, metric_id: populations.get(logrecno)}
        for logrecno, geocode in geography.items()
    ]
    return pd.DataFrame(rows).sort_values("source_block_geoid").reset_index(drop=True)
