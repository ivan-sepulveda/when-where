import { useEffect, useState } from "react";

interface CountryLookupResult {
  ip: string;
  country: string;
}

interface UseCountryResult {
  country: string | null;
  loading: boolean;
  error: string | null;
}

export function useCountry(): UseCountryResult {
  const [country, setCountry] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchCountry() {
      try {
        const response = await fetch("https://api.country.is/");
        if (!response.ok) {
          throw new Error(`country.is returned ${response.status}`);
        }
        const data: CountryLookupResult = await response.json();
        if (!cancelled) {
          setCountry(data.country);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchCountry();

    return () => {
      cancelled = true;
    };
  }, []);

  return { country, loading, error };
}
