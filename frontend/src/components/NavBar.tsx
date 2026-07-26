import { useState } from "react";
import { COUNTRIES, DEFAULT_COUNTRY_CODE } from "../lib/countries";

// No auth/user state yet -- when that lands, this is where a
// signed-in menu (profile, sign out, etc.) would slot in, mirroring
// the pattern in https://github.com/ivan-sepulveda/dft's Navbar.
const BROWSE_LINKS = [
  { label: "Destinations", href: "#" },
  { label: "About", href: "#" },
] as const;

// Only one dropdown should be open at a time.
type OpenMenu = "browse" | "country" | null;

export default function NavBar() {
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);

  // Defaults to US for now; once the IP-based country lookup
  // (see useCountry in lib/geolocateCountry.ts) is wired in, its
  // result should be used to set this instead.
  const [countryCode, setCountryCode] = useState(DEFAULT_COUNTRY_CODE);

  function toggleMenu(menu: OpenMenu) {
    setOpenMenu((current) => (current === menu ? null : menu));
  }

  return (
    <nav className="navbar">
      <a href="/" className="navbar-brand">
        when/where
      </a>

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
                <a
                  key={link.label}
                  href={link.href}
                  className="navbar-dropdown-link"
                  onClick={() => setOpenMenu(null)}
                >
                  {link.label}
                </a>
              ))}
            </div>
          )}
        </div>

        <div className="navbar-menu">
          <button
            type="button"
            className="navbar-browse-toggle"
            onClick={() => toggleMenu("country")}
            aria-expanded={openMenu === "country"}
          >
            Departing from: {countryCode} ▾
          </button>

          {openMenu === "country" && (
            <div className="navbar-dropdown navbar-dropdown-scroll">
              {COUNTRIES.map((country) => (
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
                  {country.name}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
