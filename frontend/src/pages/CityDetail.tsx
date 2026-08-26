import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import TravelAdvisoryIcon from "../components/TravelAdvisoryIcon";
import { formatDateRange } from "../lib/formatDate";
import { getCountryByCode } from "../lib/countries";
import { countryCodeToFlagEmoji } from "../lib/flagEmoji";
import { byGallerySpaceDescending, getArtMuseumsInCity, useArtMuseums } from "../lib/artMuseums";
import { getMichelinGuideUrl } from "../lib/michelin";
import { useTravelAdvisory } from "../lib/travelAdvisories";
import { getUnescoStatesPartyUrl } from "../lib/unesco";
import {
  formatDistance,
  formatMichelinCountWithinRadius,
  formatNearbyCount,
  formatUnescoCountWithinRadius,
  placeNameKey,
  useCityDetail,
  type NearbyPlaces,
} from "../lib/cityDetail";
import { fetchCityWeather, formatWeatherStats, type WeatherMetrics } from "../lib/weather";

type WeatherLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; metrics: WeatherMetrics | null }; // null = no normals for this city yet

// How many art museums the merged section below shows before cutting off --
// the backend already caps its own list, this bounds the two lists combined.
const MAX_ART_MUSEUMS = 5;

// The Aquariums & Zoos and Botanical Gardens sections: a headline count card
// plus the nearest few, or an explicit "nothing found" card. Rendered only
// when `places` is non-null -- see CityDetail's own comment at the call site
// for the null (dataset not generated) case.
//
// Unlike the UNESCO and Michelin count cards above it, the count here isn't a
// link: neither OSM nor IMLS has a per-city landing page worth sending
// someone to, and a link that just repeats the list under it would be noise.
function NearbyPlacesSection({
  heading,
  places,
  radiusKm,
  emptyMessage,
}: {
  heading: string;
  places: NearbyPlaces;
  radiusKm: number;
  emptyMessage: string;
}) {
  return (
    <>
      <h2>{heading}</h2>
      <ul className="destination-detail-stats">
        {places.count === 0 ? (
          <li className="destination-detail-stat-card">{emptyMessage}</li>
        ) : (
          <li className="destination-detail-stat-card">{formatNearbyCount(places.count, radiusKm)}</li>
        )}
        {places.places.map((place) => (
          <li
            key={`${place.name}-${place.distance_km}`}
            className="destination-detail-stat-card city-detail-nearby-card"
          >
            <span className="city-detail-nearby-name">{place.name}</span>
            <span className="city-detail-nearby-meta">
              {place.kind} · {formatDistance(place.distance_km)} · {place.source}
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}

// The city-level counterpart of DestinationDetail -- one template serving
// every city, reached by clicking a row in Destinations' "Top N Cities"
// list (or by URL: /destinations/cities/:cityId, where cityId is a
// simplemaps_id).
//
// Where DestinationDetail assembles a country's page out of several
// country-keyed files fetched straight from GitHub, almost everything
// here comes from one backend call instead -- cities have no small
// static file to fetch (see lib/cityDetail.ts's header). The exception
// is art museums, whose dataset IS small and country-keyed, so that one
// is still fetched client-side exactly the way DestinationDetail does it.
export default function CityDetail() {
  const { cityId } = useParams<{ cityId: string }>();

  // Carried over from the Destinations search (Destinations.tsx forwards
  // its own searchParams into this link), same as DestinationDetail.
  // Weather below is only fetched/shown when both dates are present --
  // "what's the weather" isn't answerable without a date range.
  const [searchParams] = useSearchParams();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const hasDateRange = Boolean(startDate && endDate);

  const cityState = useCityDetail(cityId);
  const city = cityState.status === "loaded" ? cityState.city : undefined;

  // Country-level lookups reused as-is from the country page: the travel
  // advisory and the art museum list are both published per country, not
  // per city. getCountryByCode returns a stable reference out of a
  // module-scoped map, so these effects don't re-run on every render.
  const country = city ? getCountryByCode(city.country_code) : undefined;
  const travelAdvisory = useTravelAdvisory(country);
  const artMuseums = useArtMuseums(country);

  const [weather, setWeather] = useState<WeatherLoadState>({ status: "loading" });

  useEffect(() => {
    if (!city || !startDate || !endDate) return;
    let cancelled = false;
    setWeather({ status: "loading" });

    fetchCityWeather(city.city_id, startDate, endDate)
      .then((metrics) => {
        if (cancelled) return;
        setWeather({ status: "loaded", metrics });
      })
      .catch(() => {
        if (cancelled) return;
        setWeather({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [city, startDate, endDate]);

  if (cityState.status === "loading") {
    return (
      <main className="page">
        <h1>Loading...</h1>
      </main>
    );
  }

  // Distinguished from a generic failure on purpose (see
  // lib/cityDetail.ts's CityNotFoundError): a 404 means this id isn't a
  // city at all, which is a dead end, while an error is worth retrying.
  if (cityState.status === "not-found") {
    return (
      <main className="page">
        <h1>City not found</h1>
        <p className="tagline">
          "{cityId}" isn't a city in this dataset. <Link to="/destinations?view=cities">Back to destinations</Link>
        </p>
      </main>
    );
  }

  if (cityState.status === "error" || !city) {
    return (
      <main className="page">
        <h1>Couldn't load this city</h1>
        <p className="tagline" role="alert">
          Something went wrong loading this city. Try again in a moment.{" "}
          <Link to="/destinations?view=cities">Back to destinations</Link>
        </p>
      </main>
    );
  }

  // Every name this city is known by, for the strict city-name match
  // against the art museum dataset -- see getArtMuseumsInCity(). Both
  // spellings are passed because neither side of that join has a
  // guaranteed convention: this dataset might list "Osaka" while the
  // city's own record says "Ōsaka".
  const cityNames = [city.city_ascii, city.city];
  const museumsInCity =
    artMuseums.status === "loaded" ? getArtMuseumsInCity(artMuseums.museums, cityNames) : [];

  // Two very differently-shaped sources feed one Art Museums section:
  //   * worldwide_museums.json, matched by city name -- good coverage
  //     outside the US, almost none inside it;
  //   * IMLS's US museum directory, matched by distance -- the mirror image.
  // Merged rather than shown separately, since "art museums here" is one
  // question. Anything already named by the worldwide list is dropped from
  // the IMLS half so the Met doesn't appear twice under two different labels.
  //
  // The merged list is then ranked by gallery space, biggest first, and cut
  // to MAX_ART_MUSEUMS. IMLS carries no gallery space, so those entries count
  // as zero (see byGallerySpaceDescending) and sit behind any measured
  // museum -- which is the intent: if this city has one of the world's
  // largest art museums, that should lead.
  const worldArtMuseums = museumsInCity.map((museum) => ({
    name: museum.name,
    note: "One of the world's largest art museums",
    gallerySpaceM2: museum.gallerySpaceM2 ?? 0,
  }));
  const worldArtMuseumKeys = new Set(worldArtMuseums.map((museum) => placeNameKey(museum.name)));
  const localArtMuseums = (city.local_art_museums?.places ?? [])
    .filter((place) => !worldArtMuseumKeys.has(placeNameKey(place.name)))
    .map((place) => ({
      name: place.name,
      note: `${formatDistance(place.distance_km)} · ${place.source}`,
      gallerySpaceM2: 0,
    }));
  const artMuseumEntries = [...worldArtMuseums, ...localArtMuseums]
    .sort(byGallerySpaceDescending)
    .slice(0, MAX_ART_MUSEUMS);

  return (
    <main className="page">
      <h1>
        {countryCodeToFlagEmoji(city.country_code)} {city.city_ascii}
        {travelAdvisory.status === "loaded" && travelAdvisory.advisory && (
          <TravelAdvisoryIcon advisory={travelAdvisory.advisory} />
        )}
      </h1>
      <p className="tagline">
        {/* admin_name is the state/province/prefecture, absent for the
            handful of city-states and small territories that have none. */}
        {[city.admin_name, city.country_name].filter(Boolean).join(", ")}
        {city.population !== null && ` · population ${city.population.toLocaleString("en-US")}`}
        {". "}
        <Link to={{ pathname: "/destinations", search: searchParams.toString() }}>Back to destinations</Link>
      </p>

      {hasDateRange && startDate && endDate && (
        <p className="destination-detail-dates">Your dates: {formatDateRange(startDate, endDate)}</p>
      )}

      <h2>UNESCO World Heritage Sites</h2>
      <ul className="destination-detail-stats">
        <li>
          {/* Headline count, styled and linked exactly like
              DestinationDetail's equivalent card. radius_km comes from
              the response rather than a constant here, so the label
              can't claim a radius the backend didn't filter on. */}
          <a
            href={getUnescoStatesPartyUrl(city.country_code)}
            target="_blank"
            rel="noopener noreferrer"
            className="destination-detail-stat-card destination-detail-stat-card-link"
          >
            {formatUnescoCountWithinRadius(city.unesco_site_count, city.radius_km)}
          </a>
        </li>
        {city.unesco_sites.map((site) => (
          <li key={site.name} className="destination-detail-stat-card city-detail-nearby-card">
            <span className="city-detail-nearby-name">{site.name}</span>
            <span className="city-detail-nearby-meta">
              {site.category} · {formatDistance(site.distance_km)}
            </span>
          </li>
        ))}
      </ul>

      <h2>Michelin Guide Restaurants</h2>
      <ul className="destination-detail-stats">
        <li>
          <a
            href={getMichelinGuideUrl(city.country_code)}
            target="_blank"
            rel="noopener noreferrer"
            className="destination-detail-stat-card destination-detail-stat-card-link"
          >
            {formatMichelinCountWithinRadius(city.michelin_count, city.radius_km)}
          </a>
        </li>
        {city.michelin_restaurants.length > 0 && (
          // The backend caps this list at the 10 nearest while the count
          // above is the true total, so this caption exists to keep a
          // "roughly 550 restaurants" headline over a 10-row list from
          // reading as a bug.
          <li className="city-detail-list-note">
            the {city.michelin_restaurants.length} closest to {city.city_ascii}
          </li>
        )}
        {city.michelin_restaurants.map((restaurant) => (
          <li
            key={`${restaurant.name}-${restaurant.distance_km}`}
            className="destination-detail-stat-card city-detail-nearby-card"
          >
            <span className="city-detail-nearby-name">{restaurant.name}</span>
            <span className="city-detail-nearby-meta">
              {restaurant.award} · {restaurant.cuisine} · {formatDistance(restaurant.distance_km)}
            </span>
          </li>
        ))}
      </ul>

      {hasDateRange && (
        <>
          <h2>Forecasted weather for your dates based on historical data</h2>
          {/* No "(based off Capital City of X)" note like the country
              page has -- these numbers are this city's own normals, not
              a capital-city proxy. */}
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
                No weather data available for {city.city_ascii} yet.
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

      <h2>Art Museums</h2>
      <ul className="destination-detail-stats">
        {artMuseums.status === "loading" && (
          <li className="destination-detail-stat-card">Loading art museum data...</li>
        )}
        {artMuseums.status === "error" && artMuseumEntries.length === 0 && (
          <li className="destination-detail-stat-card" role="alert">
            Couldn't load art museum data.
          </li>
        )}
        {artMuseums.status !== "loading" && artMuseumEntries.length === 0 && (
          // Worth naming what the datasets actually are: the worldwide list
          // is a curated selection with uneven per-country coverage, and the
          // per-city half is US-only, so "none" here is common and doesn't
          // mean the city has no museums.
          <li className="destination-detail-stat-card">
            No art museum near {city.city_ascii} is in this dataset (a worldwide art museum list, plus
            the US museum directory).
          </li>
        )}
        {artMuseumEntries.map((museum) => (
          <li key={museum.name} className="destination-detail-stat-card city-detail-nearby-card">
            <span className="city-detail-nearby-name">{museum.name}</span>
            <span className="city-detail-nearby-meta">{museum.note}</span>
          </li>
        ))}
      </ul>

      {/* Null means build_city_attractions.py hasn't been run in the
          backend's checkout, so these two sections are hidden entirely
          rather than asserting a city has no zoo when nothing has looked.
          A zero count, by contrast, renders as a real "nothing found" card
          inside NearbyPlacesSection. */}
      {city.zoos_and_aquariums && city.attractions_radius_km !== null && (
        <NearbyPlacesSection
          heading="Aquariums & Zoos"
          places={city.zoos_and_aquariums}
          radiusKm={city.attractions_radius_km}
          emptyMessage={`No aquariums or zoos within ${city.attractions_radius_km}km of ${city.city_ascii} in this dataset.`}
        />
      )}

      {city.botanical_gardens && city.attractions_radius_km !== null && (
        <NearbyPlacesSection
          heading="Botanical Gardens"
          places={city.botanical_gardens}
          radiusKm={city.attractions_radius_km}
          emptyMessage={`No botanical gardens within ${city.attractions_radius_km}km of ${city.city_ascii} in this dataset.`}
        />
      )}
    </main>
  );
}
