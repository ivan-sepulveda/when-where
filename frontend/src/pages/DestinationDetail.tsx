import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import CarouselLightbox, { type LightboxImage } from "../components/CarouselLightbox";
import TravelAdvisoryIcon from "../components/TravelAdvisoryIcon";
import exampleImg from "../assets/example_img.png";
import { formatDateRange } from "../lib/formatDate";
import { getCountryByCode } from "../lib/countries";
import { countryCodeToFlagEmoji } from "../lib/flagEmoji";
import { getTopArtMuseums, useArtMuseums } from "../lib/artMuseums";
import { useDepartureCountry } from "../lib/departureCountry";
import { formatHikingTrailCount, useHikingTrailCount } from "../lib/hiking";
import { formatMichelinCount, getMichelinAwardCounts, getMichelinGuideUrl } from "../lib/michelin";
import { formatShortestFlight, useShortestFlight } from "../lib/shortestFlight";
import { useTravelAdvisory } from "../lib/travelAdvisories";
import { formatUnescoCount, getUnescoSiteCounts, getUnescoStatesPartyUrl } from "../lib/unesco";
import { useCountryStatCount } from "../lib/useCountryStatCount";
import { fetchCountryWeather, formatWeatherStats, type CountryWeather } from "../lib/weather";

type WeatherLoadState =
  | { status: "loading" }
  | { status: "error" }
  | ({ status: "loaded" } & CountryWeather);

// Single switch controlling what clicking the Michelin card does --
// "link" (today's behavior: opens guide.michelin.com in a new tab),
// "lightbox" (opens the CarouselLightbox below instead), or "none"
// (plain, non-interactive card, no click handler at all). Deliberately
// one variable rather than several independent booleans so there's no
// invalid combination to accidentally leave the card in (e.g. both a
// link AND a lightbox wired to the same click).
type MichelinCardBehavior = "link" | "lightbox" | "none";
const MICHELIN_CARD_BEHAVIOR: MichelinCardBehavior = "link";

// Placeholder photo set for the Michelin lightbox -- same image three
// times with "Test N" captions, standing in for real per-country
// Michelin restaurant photos until that data exists. Swap this for a
// real per-country array (or fetch) once it does; CarouselLightbox
// itself is already generic (just an images/isOpen/onClose prop) and
// doesn't need to change.
const PLACEHOLDER_MICHELIN_IMAGES: LightboxImage[] = [
  { src: exampleImg, caption: "Test 1" },
  { src: exampleImg, caption: "Test 2" },
  { src: exampleImg, caption: "Test 3" },
];

// Placeholder page for /destinations/:country. One template serves every
// ISO 3166-1 alpha-2 code -- real content (overarching score, monthly
// breakdown, factor detail) lands here once that data is wired up.
export default function DestinationDetail() {
  const { country: countryParam } = useParams<{ country: string }>();
  const country = countryParam ? getCountryByCode(countryParam) : undefined;

  // Carried over from the Destinations search (see Destinations.tsx's
  // Link, which forwards its own searchParams). Displayed as-is, and
  // also used below to fetch date-weighted weather for this country.
  const [searchParams] = useSearchParams();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const hasDateRange = Boolean(startDate && endDate);

  const michelin = useCountryStatCount(country, getMichelinAwardCounts);
  const unesco = useCountryStatCount(country, getUnescoSiteCounts);
  const hiking = useHikingTrailCount(country);
  const artMuseums = useArtMuseums(country);
  const travelAdvisory = useTravelAdvisory(country);

  const { countryCode: departureCountryCode } = useDepartureCountry();
  const departureCountry = getCountryByCode(departureCountryCode);
  const shortestFlight = useShortestFlight(departureCountry, country);

  const [weather, setWeather] = useState<WeatherLoadState>({ status: "loading" });
  const [michelinLightboxOpen, setMichelinLightboxOpen] = useState(false);

  useEffect(() => {
    if (!country || !startDate || !endDate) return;
    let cancelled = false;
    setWeather({ status: "loading" });

    fetchCountryWeather(country.code, startDate, endDate)
      .then(({ metrics, capitalCity }) => {
        if (cancelled) return;
        setWeather({ status: "loaded", metrics, capitalCity });
      })
      .catch(() => {
        if (cancelled) return;
        setWeather({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [country, startDate, endDate]);

  if (!country) {
    return (
      <main className="page">
        <h1>Destination not found</h1>
        <p className="tagline">
          "{countryParam}" isn't a recognized country code.{" "}
          <Link to="/destinations">Back to destinations</Link>
        </p>
      </main>
    );
  }

  return (
    <main className="page">
      <h1>
        {countryCodeToFlagEmoji(country.code)} {country.name}
        {travelAdvisory.status === "loaded" && travelAdvisory.advisory && (
          <TravelAdvisoryIcon advisory={travelAdvisory.advisory} />
        )}
      </h1>
      <p className="tagline">
        Trip scores and monthly breakdowns for {country.name} are coming
        soon. <Link to="/destinations">Back to destinations</Link>
      </p>

      {hasDateRange && startDate && endDate && (
        <p className="destination-detail-dates">Your dates: {formatDateRange(startDate, endDate)}</p>
      )}

      <ul className="destination-detail-stats">
        {michelin.status === "loaded" && MICHELIN_CARD_BEHAVIOR === "link" && (
          <li>
            <a
              href={getMichelinGuideUrl(country.code)}
              target="_blank"
              rel="noopener noreferrer"
              className="destination-detail-stat-card destination-detail-stat-card-link"
            >
              {formatMichelinCount(michelin.count)}
            </a>
          </li>
        )}

        {michelin.status === "loaded" && MICHELIN_CARD_BEHAVIOR === "lightbox" && (
          <li>
            <button
              type="button"
              onClick={() => setMichelinLightboxOpen(true)}
              className="destination-detail-stat-card destination-detail-stat-card-link"
            >
              {formatMichelinCount(michelin.count)}
            </button>
          </li>
        )}

        {michelin.status === "loaded" && MICHELIN_CARD_BEHAVIOR === "none" && (
          <li className="destination-detail-stat-card">{formatMichelinCount(michelin.count)}</li>
        )}

        {michelin.status !== "loaded" && (
          <li className="destination-detail-stat-card">
            {michelin.status === "loading" && "Loading Michelin Guide data..."}
            {michelin.status === "error" && <span role="alert">Couldn't load Michelin Guide data.</span>}
          </li>
        )}

        {unesco.status === "loaded" ? (
          <li>
            <a
              href={getUnescoStatesPartyUrl(country.code)}
              target="_blank"
              rel="noopener noreferrer"
              className="destination-detail-stat-card destination-detail-stat-card-link"
            >
              {formatUnescoCount(unesco.count)}
            </a>
          </li>
        ) : (
          <li className="destination-detail-stat-card">
            {unesco.status === "loading" && "Loading UNESCO World Heritage Site data..."}
            {unesco.status === "error" && (
              <span role="alert">Couldn't load UNESCO World Heritage Site data.</span>
            )}
          </li>
        )}
      </ul>

      <h2>Shortest Flight</h2>
      <ul className="destination-detail-stats">
        {departureCountry?.code === country.code && (
          <li className="destination-detail-stat-card">
            You're departing from {country.name} -- no flight needed.
          </li>
        )}
        {departureCountry?.code !== country.code && shortestFlight.status === "loading" && (
          <li className="destination-detail-stat-card">Loading shortest flight data...</li>
        )}
        {departureCountry?.code !== country.code && shortestFlight.status === "error" && (
          <li className="destination-detail-stat-card" role="alert">
            Couldn't load shortest flight data.
          </li>
        )}
        {departureCountry?.code !== country.code &&
          shortestFlight.status === "loaded" &&
          shortestFlight.flight === null && (
            <li className="destination-detail-stat-card">
              No known flight route from {departureCountry?.name ?? "your departure country"} to{" "}
              {country.name} in this dataset.
            </li>
          )}
        {departureCountry?.code !== country.code &&
          shortestFlight.status === "loaded" &&
          shortestFlight.flight !== null && (
            <li className="destination-detail-stat-card">{formatShortestFlight(shortestFlight.flight)}</li>
          )}
      </ul>

      {hasDateRange && (
        <>
          <h2>Forecasted weather for your dates based on historical data</h2>
          {weather.status === "loaded" && weather.metrics !== null && weather.capitalCity && (
            <p className="destination-detail-weather-note">
              (based off Capital City of {weather.capitalCity})
            </p>
          )}
          <ul className="destination-detail-stats">
            {weather.status === "loading" && (
              <li className="destination-detail-stat-card">Loading weather data...</li>
            )}
            {weather.status === "error" && (
              <li className="destination-detail-stat-card" role="alert">
                Couldn't load weather data for those dates.
              </li>
            )}
            {weather.status === "loaded" && weather.metrics === null && (
              <li className="destination-detail-stat-card">
                No weather data available for {country.name} yet.
              </li>
            )}
            {weather.status === "loaded" &&
              weather.metrics !== null &&
              formatWeatherStats(weather.metrics).map((stat) => (
                <li key={stat.label} className="destination-detail-stat-card">
                  {stat.label}: {stat.value}
                </li>
              ))}
          </ul>
        </>
      )}

      <h2>Hiking and Outdoors</h2>
      <ul className="destination-detail-stats">
        {hiking.status === "loading" && (
          <li className="destination-detail-stat-card">Loading hiking trail data...</li>
        )}
        {hiking.status === "error" && (
          <li className="destination-detail-stat-card" role="alert">
            Couldn't load hiking trail data.
          </li>
        )}
        {hiking.status === "loaded" && hiking.count === null && (
          <li className="destination-detail-stat-card">
            No hiking trail data available for {country.name} yet.
          </li>
        )}
        {hiking.status === "loaded" && hiking.count !== null && (
          <li className="destination-detail-stat-card">{formatHikingTrailCount(hiking.count)}</li>
        )}
      </ul>

      <h2>Art Museums</h2>
      <ul className="destination-detail-stats">
        {artMuseums.status === "loading" && (
          <li className="destination-detail-stat-card">Loading art museum data...</li>
        )}
        {artMuseums.status === "error" && (
          <li className="destination-detail-stat-card" role="alert">
            Couldn't load art museum data.
          </li>
        )}
        {artMuseums.status === "loaded" && artMuseums.museums.length === 0 && (
          <li className="destination-detail-stat-card">
            No major art museums for {country.name} in this dataset.
          </li>
        )}
        {artMuseums.status === "loaded" &&
          getTopArtMuseums(artMuseums.museums).map((museum) => (
            <li key={museum.name} className="destination-detail-stat-card">
              {museum.name} ({museum.city})
            </li>
          ))}
      </ul>

      {MICHELIN_CARD_BEHAVIOR === "lightbox" && (
        <CarouselLightbox
          images={PLACEHOLDER_MICHELIN_IMAGES}
          isOpen={michelinLightboxOpen}
          onClose={() => setMichelinLightboxOpen(false)}
        />
      )}
    </main>
  );
}
