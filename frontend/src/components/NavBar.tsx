import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { COUNTRIES } from "../lib/countries";
import { useDepartureCountry } from "../lib/departureCountry";
import { countryCodeToFlagEmoji } from "../lib/flagEmoji";
import { normalizeForSearch } from "../lib/search";

// No auth/user state yet -- when that lands, this is where a
// signed-in menu (profile, sign out, etc.) would slot in, mirroring
// the pattern in https://github.com/ivan-sepulveda/dft's Navbar.
const BROWSE_LINKS = [{ label: "Destinations", to: "/destinations" }] as const;

// Only one dropdown should be open at a time.
type OpenMenu = "browse" | "country" | null;

export default function NavBar() {
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);

  // Shared with DestinationDetail's Shortest Flight card -- see
  // lib/departureCountry.tsx for the geolocation-default/manual-override
  // behavior.
  const { countryCode, setCountryCode } = useDepartureCountry();

  const [countrySearch, setCountrySearch] = useState("");
  const countrySearchRef = useRef<HTMLInputElement>(null);

  const trimmedSearch = countrySearch.trim();
  const displayedCountries = trimmedSearch
    ? COUNTRIES.filter((country) => {
        const haystack = normalizeForSearch(`${country.code} ${country.name}`);
        return haystack.includes(normalizeForSearch(trimmedSearch));
      })
    : COUNTRIES;

  // Every time the country dropdown opens, clear any leftover search
  // text from last time and focus the box so typing works immediately
  // -- no need to click into it or scroll to find a country.
  useEffect(() => {
    if (openMenu === "country") {
      setCountrySearch("");
      countrySearchRef.current?.focus();
    }
  }, [openMenu]);

  function toggleMenu(menu: OpenMenu) {
    setOpenMenu((current) => (current === menu ? null : menu));
  }

  return (
    <nav className="navbar">
      <Link to="/" className="navbar-brand">
        when/where
      </Link>

      <div className="navbar-links">
        <div className="navbar-menu">
          <button
            type="button"
            className="navbar-browse-toggle"
            onClick={() => toggleMenu("browse")}
            aria-expanded={openMenu === "browse"}
          >
            Browse ▾
          </button>

          {openMenu === "browse" && (
            <div className="navbar-dropdown">
              {BROWSE_LINKS.map((link) => (
                <Link
                  key={link.label}
                  to={link.to}
                  className="navbar-dropdown-link"
                  onClick={() => setOpenMenu(null)}
                >
                  {link.label}
                </Link>
              ))}
            </div>
          )}
        </div>

        <Link to="/about" className="navbar-about-link">
          About
        </Link>

        <div className="navbar-menu">
          <button
            type="button"
            className="navbar-browse-toggle"
            onClick={() => toggleMenu("country")}
            aria-expanded={openMenu === "country"}
          >
            Departing from: {countryCode} {countryCodeToFlagEmoji(countryCode)} ▾
          </button>

          {openMenu === "country" && (
            <div className="navbar-dropdown navbar-dropdown-wide">
              <input
                ref={countrySearchRef}
                type="text"
                value={countrySearch}
                onChange={(e) => setCountrySearch(e.target.value)}
                placeholder="Search countries..."
                className="navbar-dropdown-search"
              />

              <div className="navbar-dropdown-scroll">
                {displayedCountries.length === 0 && (
                  <p className="navbar-dropdown-empty">No matches</p>
                )}

                {displayedCountries.map((country) => (
                  <button
                    key={country.code}
                    type="button"
                    className="navbar-dropdown-link navbar-dropdown-option"
                    aria-current={country.code === countryCode}
                    onClick={() => {
                      setCountryCode(country.code);
                      setOpenMenu(null);
                    }}
                  >
                    {countryCodeToFlagEmoji(country.code)} {country.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
