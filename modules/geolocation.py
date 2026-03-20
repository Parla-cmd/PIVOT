"""
Geolocation / Address Module -- Sweden
Sources: Lantmäteriet open API, Nominatim (OpenStreetMap), SCB regional data
"""
import urllib.parse
import requests
from .utils import fetch, console, print_section, print_result


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
LANTMATERIET_SUGGEST = "https://api.lantmateriet.se/distribution/produkter/ortnamn/v1/suggestion"


def geocode_address(address: str) -> list[dict]:
    """
    Geocode a Swedish address using Nominatim (OpenStreetMap).
    Returns list of possible matches with coordinates.
    """
    results = []
    params = {
        "q": address,
        "format": "json",
        "countrycodes": "se",
        "addressdetails": 1,
        "limit": 5,
    }
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": "sweden-osint-educational-tool"},
            timeout=10,
        )
        if resp.status_code == 200:
            for item in resp.json():
                addr_details = item.get("address", {})
                results.append({
                    "display_name": item.get("display_name", ""),
                    "lat": item.get("lat", ""),
                    "lon": item.get("lon", ""),
                    "type": item.get("type", ""),
                    "municipality": addr_details.get("municipality", ""),
                    "county": addr_details.get("county", ""),
                    "postcode": addr_details.get("postcode", ""),
                    "country": addr_details.get("country", ""),
                    "osm_url": f"https://www.openstreetmap.org/"
                               f"?mlat={item.get('lat')}&mlon={item.get('lon')}&zoom=16",
                    "maps_url": f"https://maps.google.com/?q="
                                f"{item.get('lat')},{item.get('lon')}",
                })
    except Exception as e:
        console.print(f"  [yellow]Geocoding error: {e}[/yellow]")
    return results


def reverse_geocode(lat: str, lon: str) -> dict:
    """Reverse geocode coordinates to Swedish address."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1},
            headers={"User-Agent": "sweden-osint-educational-tool"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "display_name": data.get("display_name", ""),
                "address": data.get("address", {}),
            }
    except Exception:
        pass
    return {}


def lookup_swedish_county(municipality: str) -> str:
    """Map municipality to Swedish county (län) -- partial list."""
    county_map = {
        "Stockholm": "Stockholms län",
        "Göteborg": "Västra Götalands län",
        "Malmö": "Skåne län",
        "Uppsala": "Uppsala län",
        "Linköping": "Östergötlands län",
        "Örebro": "Örebro län",
        "Västerås": "Västmanlands län",
        "Helsingborg": "Skåne län",
        "Norrköping": "Östergötlands län",
        "Jönköping": "Jönköpings län",
        "Lund": "Skåne län",
        "Umeå": "Västernorrlands län",
        "Gävle": "Gävleborgs län",
        "Borås": "Västra Götalands län",
        "Eskilstuna": "Södermanlands län",
        "Södertälje": "Stockholms län",
        "Karlstad": "Värmlands län",
        "Täby": "Stockholms län",
        "Sundsvall": "Västernorrlands län",
        "Luleå": "Norrbottens län",
        "Östersund": "Jämtlands län",
        "Växjö": "Kronobergs län",
        "Halmstad": "Hallands län",
        "Kalmar": "Kalmar län",
        "Karlskrona": "Blekinge län",
    }
    return county_map.get(municipality, "")


def run(address: str = "", lat: str = "", lon: str = ""):
    print_section("GEOLOCATION / ADDRESS LOOKUP")

    if lat and lon:
        console.print(f"  [dim]Coordinates:[/dim] [bold]{lat}, {lon}[/bold]\n")
        console.print("  [dim]Reverse geocoding...[/dim]")
        result = reverse_geocode(lat, lon)
        if result:
            console.print("  [bold green]> Address Found[/bold green]")
            print_result("    Full address", result.get("display_name", ""))
            addr = result.get("address", {})
            for key in ("road", "house_number", "postcode", "city", "municipality",
                        "county", "country"):
                if addr.get(key):
                    print_result(f"    {key.replace('_', ' ').capitalize()}", addr[key])
            console.print(f"    [cyan]OSM: https://www.openstreetmap.org/"
                          f"?mlat={lat}&mlon={lon}&zoom=16[/cyan]")
        else:
            console.print("  [yellow]No results found.[/yellow]")
        return

    if address:
        console.print(f"  [dim]Address:[/dim] [bold]{address}[/bold]\n")
        console.print("  [dim]Geocoding via Nominatim...[/dim]")
        results = geocode_address(address)

        if not results:
            console.print("  [yellow]No results found.[/yellow]")
            return

        console.print(f"  [bold green]> {len(results)} match(es):[/bold green]\n")
        for i, r in enumerate(results, 1):
            console.print(f"  [bold green]  {i}.[/bold green] {r['display_name']}")
            if r.get("lat") and r.get("lon"):
                print_result("    Coordinates", f"{r['lat']}, {r['lon']}")
            if r.get("municipality"):
                print_result("    Municipality", r["municipality"])
                county = lookup_swedish_county(r["municipality"])
                if county:
                    print_result("    County (Län)", county)
            if r.get("postcode"):
                print_result("    Postcode", r["postcode"])
            console.print(f"    [cyan]{r['osm_url']}[/cyan]")
            console.print(f"    [dim]Google Maps: {r['maps_url']}[/dim]")
            console.print()
