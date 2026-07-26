import { useState } from "react";

// No auth/user state yet -- when that lands, this is where a
// signed-in menu (profile, sign out, etc.) would slot in, mirroring
// the pattern in https://github.com/ivan-sepulveda/dft's Navbar.
const BROWSE_LINKS = [
  { label: "Destinations", href: "#" },
  { label: "About", href: "#" },
] as const;

export default function NavBar() {
  const [browseOpen, setBrowseOpen] = useState(false);

  return (
    <nav className="navbar">
      <a href="/" className="navbar-brand">
        when/where
      </a>

      <div className="navbar-menu">
        <button
          type="button"
          className="navbar-browse-toggle"
          onClick={() => setBrowseOpen((open) => !open)}
          aria-expanded={browseOpen}
        >
          Browse ▾
        </button>

        {browseOpen && (
          <div className="navbar-dropdown">
            {BROWSE_LINKS.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="navbar-dropdown-link"
                onClick={() => setBrowseOpen(false)}
              >
                {link.label}
              </a>
            ))}
          </div>
        )}
      </div>
    </nav>
  );
}
