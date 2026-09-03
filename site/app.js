"use strict";

const RELEASE_PATH = "data/releases/poc039-v2";

const PANEL_FILES = {
  house: `${RELEASE_PATH}/pa_house_district_election_features_v2.csv`,
  senate: `${RELEASE_PATH}/pa_senate_district_election_features_v2.csv`,
};

const METRICS = [
  {
    key: "total_population_estimate",
    label: "Total population",
    shortLabel: "Population",
    format: "count",
    source: "population",
  },
  {
    key: "population_deviation_from_chamber_mean_pct",
    label: "Population deviation from chamber mean",
    shortLabel: "Deviation",
    format: "percentagePoints",
    source: "population",
  },
  {
    key: "population_per_total_sq_km",
    label: "Population per total km²",
    shortLabel: "People / km²",
    format: "density",
    source: "population",
  },
  {
    key: "education_bachelors_plus_share",
    label: "Bachelor’s degree or higher (age 25+)",
    shortLabel: "Bachelor’s+",
    format: "rate",
    source: "socioeconomic",
  },
  {
    key: "education_below_high_school_share",
    label: "Below high school (age 25+)",
    shortLabel: "Below high school",
    format: "rate",
    source: "socioeconomic",
  },
  {
    key: "employment_to_population_rate",
    label: "Employment-to-population rate",
    shortLabel: "Employment rate",
    format: "rate",
    source: "socioeconomic",
  },
  {
    key: "civilian_unemployment_rate",
    label: "Civilian unemployment rate",
    shortLabel: "Unemployment rate",
    format: "rate",
    source: "socioeconomic",
  },
  {
    key: "labor_force_participation_rate",
    label: "Labor force participation rate",
    shortLabel: "Labor participation",
    format: "rate",
    source: "socioeconomic",
  },
  {
    key: "poverty_below_poverty_line_share",
    label: "Population below poverty line",
    shortLabel: "Below poverty",
    format: "rate",
    source: "socioeconomic",
  },
  {
    key: "poverty_below_200_percent_share",
    label: "Population below 200% of poverty line",
    shortLabel: "Below 200% poverty",
    format: "rate",
    source: "socioeconomic",
  },
];

const cache = new Map();
const state = {
  chamber: "house",
  year: 2026,
  compareYear: 2024,
  metricKey: "total_population_estimate",
  district: 1,
  filter: "",
};

const elements = {
  status: document.querySelector("#status"),
  dashboard: document.querySelector("#dashboard"),
  year: document.querySelector("#year-select"),
  metric: document.querySelector("#metric-select"),
  district: document.querySelector("#district-select"),
  compare: document.querySelector("#compare-select"),
  districtFilter: document.querySelector("#district-filter"),
  selectedDistrictLabel: document.querySelector("#selected-district-label"),
  selectedValue: document.querySelector("#selected-value"),
  selectedComparison: document.querySelector("#selected-comparison"),
  statewideValue: document.querySelector("#statewide-value"),
  statewideNote: document.querySelector("#statewide-note"),
  medianValue: document.querySelector("#median-value"),
  sourceProduct: document.querySelector("#source-product"),
  sourceNote: document.querySelector("#source-note"),
  trendTitle: document.querySelector("#trend-title"),
  trendChart: document.querySelector("#trend-chart"),
  trendTooltip: document.querySelector("#trend-tooltip"),
  planLegend: document.querySelector("#plan-legend"),
  detailElection: document.querySelector("#detail-election"),
  detailPlan: document.querySelector("#detail-plan"),
  detailPopSource: document.querySelector("#detail-pop-source"),
  detailSocioSource: document.querySelector("#detail-socio-source"),
  detailUncertainty: document.querySelector("#detail-uncertainty"),
  detailContest: document.querySelector("#detail-contest"),
  metricColumnLabel: document.querySelector("#metric-column-label"),
  compareColumnLabel: document.querySelector("#compare-column-label"),
  rankingBody: document.querySelector("#ranking-body"),
  tableCount: document.querySelector("#table-count"),
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    const nextCharacter = text[index + 1];

    if (character === '"' && quoted && nextCharacter === '"') {
      field += '"';
      index += 1;
    } else if (character === '"') {
      quoted = !quoted;
    } else if (character === "," && !quoted) {
      row.push(field);
      field = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && nextCharacter === "\n") index += 1;
      row.push(field);
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }

  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  const [headers, ...records] = rows;
  return records.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

async function loadPanel(chamber) {
  if (cache.has(chamber)) return cache.get(chamber);

  const response = await fetch(PANEL_FILES[chamber]);
  if (!response.ok) throw new Error(`Could not load the ${chamber} panel (${response.status}).`);
  const records = parseCsv(await response.text());
  cache.set(chamber, records);
  return records;
}

function numberValue(record, key) {
  const rawValue = record?.[key];
  if (rawValue === undefined || rawValue === null || String(rawValue).trim() === "") return null;
  const value = Number(rawValue);
  return Number.isFinite(value) ? value : null;
}

function currentMetric() {
  return METRICS.find((metric) => metric.key === state.metricKey) ?? METRICS[0];
}

function formatValue(value, metric = currentMetric()) {
  if (!Number.isFinite(value)) return "Not available";

  if (metric.format === "rate") {
    return new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 }).format(value);
  }

  if (metric.format === "percentagePoints") {
    return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
  }

  if (metric.format === "density") {
    return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value)} / km²`;
  }

  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatDelta(value, metric = currentMetric()) {
  if (!Number.isFinite(value)) return "—";
  const prefix = value > 0 ? "+" : "";
  if (metric.format === "rate") return `${prefix}${(value * 100).toFixed(1)} pts`;
  if (metric.format === "percentagePoints") return `${prefix}${value.toFixed(1)} pts`;
  if (metric.format === "density") return `${prefix}${Math.round(value).toLocaleString("en-US")} / km²`;
  return `${prefix}${Math.round(value).toLocaleString("en-US")}`;
}

function chamberLabel(chamber = state.chamber) {
  return chamber === "house" ? "House" : "Senate";
}

function planStyle(record) {
  const styles = {
    "1991": { color: "#137f78", label: "1991 plan" },
    "2001": { color: "#b54d3b", label: "2001 plan" },
    "2012": { color: "#b9821f", label: "2012 plan" },
    "2021": { color: "#285b75", label: "2021 plan" },
  };
  return styles[record.target_plan_reference_vintage] ?? { color: "#40555d", label: "Other plan" };
}

function sourceLabel(record, metric = currentMetric()) {
  return metric.source === "population"
    ? record.population_source_product_id
    : record.socioeconomic_source_product_id;
}

function sourceYear(record, metric = currentMetric()) {
  return metric.source === "population"
    ? record.population_source_year
    : record.socioeconomic_source_year;
}

function sourcePeriod(record, metric = currentMetric()) {
  const prefix = metric.source === "population" ? "population" : "socioeconomic";
  return `${record[`${prefix}_source_period_start`]} to ${record[`${prefix}_source_period_end`]}`;
}

function setOptions(select, entries, selected) {
  select.replaceChildren(
    ...entries.map(({ value, label }) => {
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = label;
      option.selected = String(value) === String(selected);
      return option;
    }),
  );
}

function populateStaticControls(records) {
  const years = [...new Set(records.map((record) => Number(record.election_year)))].sort((a, b) => b - a);
  const districts = [...new Set(records.map((record) => Number(record.district_id)))].sort((a, b) => a - b);

  if (!years.includes(state.year)) state.year = years[0];
  if (!years.includes(state.compareYear) || state.compareYear === state.year) {
    state.compareYear = years.find((year) => year < state.year) ?? null;
  }
  if (!districts.includes(state.district)) state.district = districts[0];

  setOptions(elements.year, years.map((year) => ({ value: year, label: year })), state.year);
  setOptions(
    elements.compare,
    [
      { value: "", label: "No comparison" },
      ...years.filter((year) => year !== state.year).map((year) => ({ value: year, label: String(year) })),
    ],
    state.compareYear ?? "",
  );
  setOptions(
    elements.district,
    districts.map((district) => ({ value: district, label: `${chamberLabel()} District ${district}` })),
    state.district,
  );
}

function readUrlState() {
  const params = new URLSearchParams(window.location.search);
  const chamber = params.get("chamber");
  const year = Number(params.get("year"));
  const compareYear = Number(params.get("compare"));
  const metricKey = params.get("metric");
  const district = Number(params.get("district"));

  if (chamber === "house" || chamber === "senate") state.chamber = chamber;
  if (Number.isInteger(year)) state.year = year;
  if (Number.isInteger(compareYear)) state.compareYear = compareYear;
  if (METRICS.some((metric) => metric.key === metricKey)) state.metricKey = metricKey;
  if (Number.isInteger(district) && district > 0) state.district = district;
}

function writeUrlState() {
  const params = new URLSearchParams({
    chamber: state.chamber,
    year: String(state.year),
    metric: state.metricKey,
    district: String(state.district),
  });
  if (state.compareYear) params.set("compare", String(state.compareYear));
  window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const midpoint = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[midpoint] : (sorted[midpoint - 1] + sorted[midpoint]) / 2;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function comparisonFor(record, records) {
  if (!state.compareYear) return null;
  return records.find(
    (candidate) =>
      Number(candidate.election_year) === state.compareYear &&
      Number(candidate.district_id) === Number(record.district_id),
  );
}

function renderSummary(selected, yearRows, records) {
  const metric = currentMetric();
  const value = numberValue(selected, metric.key);
  const comparison = comparisonFor(selected, records);
  const comparisonValue = numberValue(comparison, metric.key);
  const changedPlan = comparison && comparison.target_plan_id !== selected.target_plan_id;
  const values = yearRows.map((record) => numberValue(record, metric.key)).filter(Number.isFinite);

  elements.selectedDistrictLabel.textContent = `${chamberLabel()} District ${selected.district_id} · ${state.year}`;
  elements.selectedValue.textContent = formatValue(value, metric);

  if (comparison && Number.isFinite(comparisonValue)) {
    const delta = value - comparisonValue;
    elements.selectedComparison.textContent = `${formatDelta(delta, metric)} from ${state.compareYear}${changedPlan ? " · plan changed" : ""}`;
  } else {
    elements.selectedComparison.textContent = "No comparison selected";
  }

  const statewide = numberValue(selected, "statewide_population_estimate");
  elements.statewideValue.textContent = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(statewide);
  elements.statewideNote.textContent = `Pennsylvania · ${state.year}`;
  elements.medianValue.textContent = formatValue(median(values), metric);
  elements.sourceProduct.textContent = sourceLabel(selected, metric);
  elements.sourceNote.textContent = `${sourceYear(selected, metric)} · ${sourcePeriod(selected, metric)}`;
}

function renderDetails(record) {
  elements.detailElection.textContent = `${record.election_year} general election · ${record.election_date}`;
  elements.detailPlan.textContent = record.target_plan_id.replaceAll("_", " ");
  elements.detailPopSource.textContent = `${record.population_source_product_id} (${record.population_source_period_start} to ${record.population_source_period_end})`;
  elements.detailSocioSource.textContent = `${record.socioeconomic_source_product_id} (${record.socioeconomic_source_period_start} to ${record.socioeconomic_source_period_end})`;
  elements.detailUncertainty.textContent = currentMetric().source === "population"
    ? record.population_moe_status.replaceAll("_", " ")
    : record.socioeconomic_moe_status.replaceAll("_", " ");
  elements.detailContest.textContent = record.regular_contest === "True" ? "Yes" : "No — Senate class not regularly contested";
}

function tooltipPosition(point) {
  const chartBounds = elements.trendChart.getBoundingClientRect();
  const pointBounds = point.getBoundingClientRect();
  const rawLeft = pointBounds.left + pointBounds.width / 2 - chartBounds.left;
  const halfWidth = elements.trendTooltip.offsetWidth / 2;
  const left = Math.max(halfWidth + 8, Math.min(chartBounds.width - halfWidth - 8, rawLeft));

  elements.trendTooltip.style.left = `${left}px`;
  elements.trendTooltip.style.top = `${pointBounds.top - chartBounds.top}px`;
}

function showTrendTooltip(point, record, metric) {
  const style = planStyle(record);
  elements.trendTooltip.innerHTML = `<strong>${record.election_year} · ${style.label}</strong>
    <span class="tooltip-value">${escapeHtml(formatValue(record.value, metric))}</span>
    <span>${escapeHtml(record.target_plan_id.replaceAll("_", " "))}</span>
    <span>Source: ${escapeHtml(sourceLabel(record, metric))}</span>`;
  elements.trendTooltip.hidden = false;
  tooltipPosition(point);
}

function hideTrendTooltip() {
  elements.trendTooltip.hidden = true;
}

function bindTrendTooltips(history, metric) {
  elements.trendChart.querySelectorAll(".trend-point").forEach((point) => {
    const record = history[Number(point.dataset.historyIndex)];
    point.addEventListener("mouseenter", () => showTrendTooltip(point, record, metric));
    point.addEventListener("focus", () => showTrendTooltip(point, record, metric));
    point.addEventListener("mouseleave", hideTrendTooltip);
    point.addEventListener("blur", hideTrendTooltip);
  });
}

function renderTrend(records) {
  const metric = currentMetric();
  const history = records
    .filter((record) => Number(record.district_id) === state.district)
    .map((record) => ({ ...record, value: numberValue(record, metric.key) }))
    .filter((record) => Number.isFinite(record.value))
    .sort((a, b) => Number(a.election_year) - Number(b.election_year));

  elements.trendTitle.textContent = `${chamberLabel()} District ${state.district} · ${metric.shortLabel}`;
  elements.trendChart.setAttribute(
    "aria-label",
    `${metric.label} for ${chamberLabel()} District ${state.district} from ${history[0]?.election_year ?? ""} to ${history.at(-1)?.election_year ?? ""}`,
  );

  if (history.length < 2) {
    elements.trendChart.textContent = "Not enough observations to chart.";
    elements.planLegend.replaceChildren();
    return;
  }

  const width = 760;
  const height = 270;
  const margin = { top: 20, right: 24, bottom: 36, left: 74 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const values = history.map((record) => record.value);
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * 0.12, Math.abs(maximum || 1) * 0.02);
  minimum -= padding;
  maximum += padding;
  const x = (index) => margin.left + (index / (history.length - 1)) * chartWidth;
  const y = (value) => margin.top + ((maximum - value) / (maximum - minimum || 1)) * chartHeight;

  const groups = [];
  let group = [];
  history.forEach((record, index) => {
    if (group.length && group.at(-1).target_plan_id !== record.target_plan_id) {
      groups.push(group);
      group = [];
    }
    group.push({ ...record, index });
  });
  if (group.length) groups.push(group);

  elements.planLegend.innerHTML = groups
    .map((planGroup) => {
      const style = planStyle(planGroup[0]);
      return `<span><i class="legend-swatch" style="--plan-color: ${style.color}"></i>${style.label}</span>`;
    })
    .join("");

  const gridLines = [0, 0.5, 1]
    .map((ratio) => {
      const gridValue = maximum - (maximum - minimum) * ratio;
      const gridY = margin.top + chartHeight * ratio;
      return `<line class="grid-line" x1="${margin.left}" y1="${gridY}" x2="${width - margin.right}" y2="${gridY}" />
        <text class="axis-label" x="${margin.left - 10}" y="${gridY + 4}" text-anchor="end">${escapeHtml(formatValue(gridValue, metric))}</text>`;
    })
    .join("");

  const paths = groups
    .map((planGroup) => {
      const path = planGroup.map((record, index) => `${index === 0 ? "M" : "L"}${x(record.index)},${y(record.value)}`).join(" ");
      return `<path class="trend-line" style="--plan-color: ${planStyle(planGroup[0]).color}" d="${path}" />`;
    })
    .join("");

  const bridges = groups
    .slice(1)
    .map((planGroup, index) => {
      const previous = groups[index].at(-1);
      const current = planGroup[0];
      return `<line class="plan-bridge" x1="${x(previous.index)}" y1="${y(previous.value)}" x2="${x(current.index)}" y2="${y(current.value)}">
        <title>Plan changed from ${escapeHtml(previous.target_plan_id)} to ${escapeHtml(current.target_plan_id)}</title>
      </line>`;
    })
    .join("");

  const points = history
    .map((record, index) => {
      const selected = Number(record.election_year) === state.year ? " selected" : "";
      return `<circle class="trend-point${selected}" style="--plan-color: ${planStyle(record).color}" cx="${x(index)}" cy="${y(record.value)}" r="${selected ? 6 : 4}" tabindex="0" data-history-index="${index}" aria-label="${record.election_year}: ${escapeHtml(formatValue(record.value, metric))}, ${planStyle(record).label}, source ${escapeHtml(sourceLabel(record, metric))}">
        <title>${record.election_year}: ${escapeHtml(formatValue(record.value, metric))} · ${escapeHtml(record.target_plan_id)}</title>
      </circle>`;
    })
    .join("");

  const yearLabels = history
    .filter((_, index) => index === 0 || index === history.length - 1 || index % 4 === 0)
    .map((record) => {
      const index = history.indexOf(record);
      return `<text class="axis-label" x="${x(index)}" y="${height - 12}" text-anchor="middle">${record.election_year}</text>`;
    })
    .join("");

  elements.trendChart.innerHTML = `<div id="trend-tooltip" class="chart-tooltip" role="tooltip" hidden></div>
    <svg viewBox="0 0 ${width} ${height}" focusable="false">
    ${gridLines}${bridges}${paths}${points}${yearLabels}
  </svg>`;
  elements.trendTooltip = document.querySelector("#trend-tooltip");
  bindTrendTooltips(history, metric);
}

function renderRanking(yearRows, records) {
  const metric = currentMetric();
  const ranked = yearRows
    .map((record) => ({ record, value: numberValue(record, metric.key) }))
    .filter(({ value }) => Number.isFinite(value))
    .sort((left, right) => right.value - left.value)
    .map((entry, index) => ({ ...entry, rank: index + 1 }));

  const filtered = ranked.filter(({ record }) => String(record.district_id).includes(state.filter));
  elements.metricColumnLabel.textContent = metric.shortLabel;
  elements.compareColumnLabel.textContent = state.compareYear ? `Change from ${state.compareYear}` : "Change";

  elements.rankingBody.innerHTML = filtered
    .map(({ record, value, rank }) => {
      const comparison = comparisonFor(record, records);
      const comparisonValue = numberValue(comparison, metric.key);
      const delta = Number.isFinite(comparisonValue) ? value - comparisonValue : null;
      const deltaClass = delta > 0 ? "positive" : delta < 0 ? "negative" : "";
      const selectedClass = Number(record.district_id) === state.district ? "selected-row" : "";
      return `<tr class="${selectedClass}">
        <td>${rank}</td>
        <td><button class="district-button" type="button" data-district="${record.district_id}">${chamberLabel()} ${record.district_id}</button></td>
        <td class="metric-value">${escapeHtml(formatValue(value, metric))}</td>
        <td class="${deltaClass}">${escapeHtml(formatDelta(delta, metric))}</td>
        <td>${escapeHtml(sourceLabel(record, metric))}</td>
      </tr>`;
    })
    .join("");

  elements.rankingBody.querySelectorAll("[data-district]").forEach((button) => {
    button.addEventListener("click", () => {
      state.district = Number(button.dataset.district);
      elements.district.value = String(state.district);
      render(records);
      document.querySelector(".summary-grid").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  elements.tableCount.textContent = `Showing ${filtered.length} of ${ranked.length} districts, ranked highest to lowest.`;
}

function render(records) {
  const yearRows = records.filter((record) => Number(record.election_year) === state.year);
  const selected = yearRows.find((record) => Number(record.district_id) === state.district) ?? yearRows[0];
  if (!selected) return;
  state.district = Number(selected.district_id);

  renderSummary(selected, yearRows, records);
  renderDetails(selected);
  renderTrend(records);
  renderRanking(yearRows, records);
  writeUrlState();
}

async function changeChamber(chamber) {
  state.chamber = chamber;
  document.querySelectorAll("[data-chamber]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.chamber === chamber));
  });
  elements.status.hidden = false;
  elements.status.classList.remove("error");
  elements.status.textContent = `Loading the ${chamberLabel()} panel…`;
  elements.dashboard.hidden = true;

  try {
    const records = await loadPanel(chamber);
    populateStaticControls(records);
    elements.status.hidden = true;
    elements.dashboard.hidden = false;
    render(records);
  } catch (error) {
    elements.status.classList.add("error");
    elements.status.textContent = `${error.message} Try reloading the page or use the downloadable CSV files.`;
  }
}

function bindControls() {
  document.querySelectorAll("[data-chamber]").forEach((button) => {
    button.addEventListener("click", () => changeChamber(button.dataset.chamber));
  });

  elements.year.addEventListener("change", async () => {
    state.year = Number(elements.year.value);
    if (state.compareYear === state.year) state.compareYear = null;
    const records = await loadPanel(state.chamber);
    populateStaticControls(records);
    render(records);
  });

  elements.metric.addEventListener("change", async () => {
    state.metricKey = elements.metric.value;
    render(await loadPanel(state.chamber));
  });

  elements.district.addEventListener("change", async () => {
    state.district = Number(elements.district.value);
    render(await loadPanel(state.chamber));
  });

  elements.compare.addEventListener("change", async () => {
    state.compareYear = elements.compare.value ? Number(elements.compare.value) : null;
    render(await loadPanel(state.chamber));
  });

  elements.districtFilter.addEventListener("input", async () => {
    state.filter = elements.districtFilter.value.trim();
    render(await loadPanel(state.chamber));
  });
}

async function initialize() {
  readUrlState();
  setOptions(elements.metric, METRICS.map((metric) => ({ value: metric.key, label: metric.label })), state.metricKey);
  bindControls();
  await changeChamber(state.chamber);
}

initialize();
