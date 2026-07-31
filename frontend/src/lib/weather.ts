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

// Display order/labels for DestinationDetail's weather cards. E.g.
// avg_sunshine_hours=8.6 -> "Est. Daily Sunlight Hours: 8.6".
const WEATHER_STAT_DEFS: {
  key: keyof WeatherMetrics;
  label: string;
  format: (value: number) => string;
}[] = [
  { key: "avg_high_c", label: "Est. Daily High", format: (v) => `${v.toFixed(1)}°C` },
  { key: "avg_low_c", label: "Est. Daily Low", format: (v) => `${v.toFixed(1)}°C` },
  { key: "total_precipitation_mm", label: "Est. Total Precipitation", format: (v) => `${v.toFixed(1)}mm` },
  { key: "avg_precipitation_hours_per_day", label: "Est. Daily Precipitation Hours", format: (v) => v.toFixed(1) },
  { key: "rainy_days", label: "Est. Rainy Days", format: (v) => v.toFixed(0) },
  { key: "avg_sunshine_hours", label: "Est. Daily Sunlight Hours", format: (v) => v.toFixed(1) },
];

export function formatWeatherStats(metrics: WeatherMetrics): { label: string; value: string }[] {
  return WEATHER_STAT_DEFS.map(({ key, label, format }) => ({
    label,
    value: format(metrics[key]),
  }));
}
