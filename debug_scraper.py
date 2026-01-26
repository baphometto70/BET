import json
import re
import requests
from urllib.parse import quote
from datetime import datetime
import unicodedata
from typing import Optional, List

UA = {"User-Agent": "Mozilla/5.0 (compatible; ScommesseFree/2.0)"}
DEFAULT_XG_VALUE = 1.2

def season_from_date(date_iso: str) -> int:
    dt = datetime.fromisoformat(date_iso[:10])
    return dt.year if dt.month >= 7 else dt.year - 1

def understat_team_url(team: str, date_iso: str) -> str:
    season = season_from_date(date_iso)
    return f"https://understat.com/team/{quote(team)}/{season}"

def _extract_json_from_understat(html: str, varname: str) -> Optional[list]:
    """
    Estrae un oggetto JSON da una variabile JavaScript all'interno di un tag <script> nel codice HTML.
    È progettato per essere robusto a cambiamenti minori nel formato della pagina.
    """
    script_tag_pattern = re.compile(rf"<script>.*?\b{re.escape(varname)}\b.*?</script>", re.DOTALL)
    match = script_tag_pattern.search(html)
    
    if not match:
        print(f"DEBUG: Script tag containing '{varname}' not found.")
        return None
        
    script_content = match.group(0)

    data_pattern = re.search(
        rf"\b{re.escape(varname)}\s*=\s*(?:JSON\.parse\(\s*'((?:\\.|[^'])*)'\s*\)|(\[.*?\]|\{{.*?\}}))\s*;",
        script_content,
        re.DOTALL
    )

    if not data_pattern:
        print(f"DEBUG: Data pattern for '{varname}' not found in script content.")
        return None

    escaped_json_str = data_pattern.group(1)
    literal_json_str = data_pattern.group(2)

    json_to_parse = None
    if escaped_json_str:
        try:
            json_to_parse = bytes(escaped_json_str, "utf-8").decode("unicode_escape")
        except Exception as e:
            print(f"DEBUG: Error decoding escaped JSON: {e}")
            return None
    elif literal_json_str:
        json_to_parse = literal_json_str

    if json_to_parse:
        try:
            return json.loads(json_to_parse)
        except json.JSONDecodeError as e:
            print(f"DEBUG: Error parsing JSON: {e}")
            return None
            
    print("DEBUG: No JSON data found to parse.")
    return None

def debug_scraper(team_name: str, date: str):
    url = understat_team_url(team_name, date)
    print(f"Fetching URL: {url}")
    
    try:
        resp = requests.get(url, headers=UA, timeout=30)
        resp.raise_for_status()
        html = resp.text
        
        print("Successfully fetched HTML content.")
        
        data = _extract_json_from_understat(html, "matchesData")
        
        if data:
            print("Successfully extracted matchesData!")
            # Print the first 3 matches for brevity
            print(json.dumps(data[:3], indent=2))
        else:
            print("Failed to extract matchesData.")
            # Save the HTML for inspection
            with open("understat_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved HTML content to understat_debug.html for manual inspection.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")

if __name__ == "__main__":
    # Test with a known team and recent date
    debug_scraper("Napoli", "2025-12-01")
