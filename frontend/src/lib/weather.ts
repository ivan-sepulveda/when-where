import { API_BASE_URL } from "./apiBaseUrl";

// Mirrors backend/app/main.py's WeatherDetail model.
export interface WeatherMetrics {
  avg_high_c: number;
  avg_low_c: number;
  total_precipitation_mm: number;
  avg_precipitation_hours_per_day: number;
  rainy_days: number;
  avg_sunshine_hours: number;
}

interface CountryWeatherResponse {
  country: string;
  start_date: string;
  end_date: string;
  month_weights: Record<string, number>;
  weather: WeatherMetrics | null;
  capital_city: string | null;
}

export interface CountryWeather {
  metrics: WeatherMetrics | null;
  // The primary capital city this weather is actually resolved from
  // (e.g. "Tokyo" for Japan) -- weather here comes from one
  // representative capital, not a national average, so the UI should
  // caption it as such rather than implying country-wide data.
  capitalCity: string | null;
}

// Day-weighted average of a country's raw weather metrics over a trip's
// date range -- see backend/app/scoring.py's resolve_weather_metrics().
// metrics is null if this project has no weather data for that country
// at all (not an error -- see backend/app/data_loader.py's docstring for
// why coverage is a subset of all countries).
export async function fetchCountryWeather(
  countryCode: string,
  startDate: string,
  endDate: string,
): Promise<CountryWeather> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  const res = await fetch(`${API_BASE_URL}/api/destinations/${countryCode}/weather?${params.toString()}`);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as CountryWeatherResponse;
  return { metrics: payload.weather, capitalCity: payload.capital_city };
}

interface CityWeatherResponse {
  city_id: string;
  city_ascii: string;
  start_date: string;
  end_date: string;
  month_weights: Record<string, number>;
  weather: WeatherMetrics | null;
}

// City-level counterpart of fetchCountryWeather() above -- same metrics,
// resolved from the city's OWN normals rather than its country's primary
// capital, which is why there's no capitalCity here to caption them
// with. Resolves to null (not an error) for a city whose normals haven't
// been pulled yet -- roughly 1,770 of 3,069 cities are covered so far,
// see backend/app/data_loader.py's load_city_weather_metrics().
export async function fetchCityWeather(
  cityId: string,
  startDate: string,
  endDate: string,
): Promise<WeatherMetrics | null> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  const res = await fetch(
    `${API_BASE_URL}/api/destinations/cities/${encodeURIComponent(cityId)}/weather?${params.toString()}`,
  );
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as CityWeatherResponse;
  return payload.weather;
}

const celsiusToFahrenheit = (c: number) => Math.round((c * 9) / 5 + 32);
const mmToInches = (mm: number) => Math.round(mm / 25.4);

// rainy_days is an estimate (see backend/app/scoring.py's
// resolve_rainy_days_estimate), not an exact count -- shown as a
// low-high range rather than false-precision single number.
// formatRainyDaysRange(1.82) -> "1-2", formatRainyDaysRange(5) -> "5-6"
// (always rounds down for the low end and up for the high end, even
// when the estimate already lands on a whole number).
function formatRainyDaysRange(v: number): string {
  const low = Math.floor(v);
  return `${low}-${low + 1}`;
}

// Display order/labels for DestinationDetail's weather cards. E.g.
// avg_sunshine_hours=8.6 -> "Daily Sunlight Hours: 8.6". Temperatures and
// total precipitation also show a rounded-to-the-nearest-integer
// imperial conversion alongside the metric value (source data is
// already metric -- see fetch_weather_normals.py).
const WEATHER_STAT_DEFS: {
  key: keyof WeatherMetrics;
  label: string;
  format: (value: number) => string;
}[] = [
  {
    key: "avg_high_c",
    label: "Daily High",
    format: (v) => `${v.toFixed(1)}°C / ${celsiusToFahrenheit(v)}°F`,
  },
  {
    key: "avg_low_c",
    label: "Daily Low",
    format: (v) => `${v.toFixed(1)}°C / ${celsiusToFahrenheit(v)}°F`,
  },
  {
    key: "total_precipitation_mm",
    label: "Total Precipitation",
    format: (v) => `${v.toFixed(1)}mm/${mmToInches(v)}in`,
  },
  { key: "avg_precipitation_hours_per_day", label: "Daily Precipitation Hours", format: (v) => v.toFixed(1) },
  { key: "rainy_days", label: "Rainy Days", format: formatRainyDaysRange },
  { key: "avg_sunshine_hours", label: "Daily Sunlight Hours", format: (v) => v.toFixed(1) },
];

export function formatWeatherStats(metrics: WeatherMetrics): { label: string; value: string }[] {
  return WEATHER_STAT_DEFS.map(({ key, label, format }) => ({
    label,
    value: format(metrics[key]),
  }));
}
