// Single source of truth for "which country is the user departing
// from." Previously this only lived inside NavBar's own component
// state -- invisible to every other page, including DestinationDetail's
// Shortest Flight card, which needs to know it too. Lifted into a
// context so both can read/write the same value.
//
// Defaults to an IP-based guess (see lib/geolocateCountry.ts's
// useCountry(), which hits api.country.is) and falls back to
// DEFAULT_COUNTRY_CODE if that lookup fails or hasn't resolved yet. A
// manual pick in NavBar's "Departing from" dropdown always overrides the
// geolocated guess from then on, for the rest of the session.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { DEFAULT_COUNTRY_CODE } from "./countries";
import { useCountry } from "./geolocateCountry";

interface DepartureCountryContextValue {
  countryCode: string;
  setCountryCode: (code: string) => void;
}

const DepartureCountryContext = createContext<DepartureCountryContextValue | null>(null);

export function DepartureCountryProvider({ children }: { children: ReactNode }) {
  const { country: geolocatedCountry } = useCountry();
  const [countryCode, setCountryCodeState] = useState(DEFAULT_COUNTRY_CODE);
  const [manuallySet, setManuallySet] = useState(false);

  // Only adopt the geolocated guess if the user hasn't manually picked a
  // country yet -- geolocation resolves asynchronously (after the IP
  // lookup completes), so without this guard it would silently clobber
  // a manual pick made in the meantime.
  useEffect(() => {
    if (!manuallySet && geolocatedCountry) {
      setCountryCodeState(geolocatedCountry);
    }
  }, [geolocatedCountry, manuallySet]);

  function setCountryCode(code: string) {
    setManuallySet(true);
    setCountryCodeState(code);
  }

  return (
    <DepartureCountryContext.Provider value={{ countryCode, setCountryCode }}>
      {children}
    </DepartureCountryContext.Provider>
  );
}

export function useDepartureCountry(): DepartureCountryContextValue {
  const ctx = useContext(DepartureCountryContext);
  if (!ctx) {
    throw new Error("useDepartureCountry must be used within a DepartureCountryProvider");
  }
  return ctx;
}
