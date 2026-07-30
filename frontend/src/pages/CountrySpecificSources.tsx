// Not linked from NavBar on purpose -- reachable directly at
// /country-specific-sources. Lists the per-country/region tourism data
// sources pulled in data/ (see data/README.md's "Sources" section and
// each script's own docstring for the full reasoning per source).
// Unlike the four sources on the About page, none of these currently
// feed the overarching trip score or anything else shown to users yet
// -- see compute_peak_tourism_indicator.py.
interface Source {
  name: string;
  // Omitted where the underlying script's docstring has no confirmed
  // URL yet (Colombia, Costa Rica) -- rendered as plain text rather
  // than a guessed link.
  url?: string;
}

const SOURCES_BY_CONTINENT: { continent: string; sources: Source[] }[] = [
  {
    continent: "Americas",
    sources: [
      { name: "Statistics Canada (airport itinerant movements)", url: "https://www.statcan.gc.ca" },
      {
        name: "Mexico AFAC (international air passengers)",
        url: "https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404",
      },
      {
        name: "Chile INE (monthly tourism accommodation survey)",
        url: "https://www.ine.gob.cl/estadisticas-por-tema/comercio-y-servicios/actividad-mensual-del-turismo",
      },
      { name: "Argentina INDEC (international air travel)", url: "https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-13-55" },
      { name: "Brazil (UN Tourism Dashboard)", url: "https://www.untourism.int/tourism-data/un-tourism-tourism-dashboard" },
      { name: "Colombia (Migración Colombia / OEE-MinCIT)" },
      { name: "Paraguay INE (tourism by month)", url: "https://www.ine.gov.py" },
      { name: "Uruguay Ministerio de Turismo (tourism spending)", url: "https://turismo.gub.uy/observatorio/turismoReceptivo.html" },
      { name: "Costa Rica (Banco Central de Costa Rica, hotel occupancy)" },
    ],
  },
  {
    continent: "Europe",
    sources: [{ name: "Eurostat (air passengers + crime statistics)", url: "https://ec.europa.eu/eurostat" }],
  },
  {
    continent: "Oceania",
    sources: [
      {
        name: "Australian Bureau of Statistics (visitor arrivals)",
        url: "https://www.abs.gov.au/statistics/industry/tourism-and-transport/overseas-arrivals-and-departures-australia/latest-release",
      },
      { name: "Stats NZ (visitor arrivals)", url: "https://www.stats.govt.nz" },
    ],
  },
  {
    continent: "Asia",
    sources: [
      { name: "Japan e-Stat (tourism indicators)", url: "https://dashboard.e-stat.go.jp/en/static/api" },
      { name: "Maldives Monetary Authority (tourism indicators)", url: "https://database.mma.gov.mv/monthly-statistics/real/tourism-indicators" },
      {
        name: "Indonesia BPS-Statistics (tourist visits)",
        url: "https://www.bps.go.id/en/statistics-table/2/MTQ3MCMy/tourist-visits-abroad-by-month.html",
      },
      { name: "Vietnam National Administration of Tourism (visitor arrivals)", url: "https://vietnamtourism.gov.vn/en/statistic/international" },
    ],
  },
];

export default function CountrySpecificSources() {
  return (
    <main className="page">
      <h1>Country-specific sources</h1>
      <p className="tagline">
        Per-country/region tourism data pulled into this project, on top
        of the global sources on the About page.
      </p>

      {SOURCES_BY_CONTINENT.map((group) => (
        <div key={group.continent}>
          <h2>{group.continent}</h2>
          <ul className="about-sources">
            {group.sources.map((source) => (
              <li key={source.name}>
                {source.url ? (
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.name}
                  </a>
                ) : (
                  source.name
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </main>
  );
}
