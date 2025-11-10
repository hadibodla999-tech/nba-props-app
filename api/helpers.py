"""
api/helpers.py
Robust helpers for fetching NBA data using nba_api v1.10.x.
Includes retries, rate-limits, headers, and retry loops for all endpoints.
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

# nba_api imports (v1.10.x compatible)
from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import (
    playergamelog,
    scoreboardv2,
    leaguedashteamstats,
    commonteamroster,
    commonplayerinfo,
)

# --- BROWSER HEADERS ---
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Host': 'stats.nba.com',
    'Origin': 'https://www.nba.com',
    'Referer': 'https://www.nba.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
}
# --- END NEW ---

# --- NEW: GLOBAL RETRY WRAPPER ---
def _nba_api_request_wrapper(api_call_function, call_name):
    """
    Aggressively retries any nba_api function that fails.
    """
    MAX_RETRIES = 5
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[helpers] [{call_name}] Attempt {attempt}/{MAX_RETRIES}...")
        try:
            # Run the provided function (which is a lambda)
            result = api_call_function() 
            print(f"[helpers] [{call_name}] Success.")
            return result # Return on success
        except Exception as e:
            print(f"[helpers] [{call_name}] Attempt {attempt} failed: {e}")
            if attempt == MAX_RETRIES:
                print(f"[helpers] [{call_name}] All retries failed.")
                return None # Failed all attempts
            
            sleep_time = 5 * attempt # 5s, 10s, 15s, 20s
            print(f"[helpers] Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)
# --- END NEW ---


# Map from human team name to abbreviation for DVP scraping fallback
TEAM_NAME_TO_ABBREV = {
    'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BKN',
    'Charlotte Hornets': 'CHA', 'Chicago Bulls': 'CHI', 'Cleveland Cavaliers': 'CLE',
    'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN', 'Detroit Pistons': 'DET',
    'Golden State Warriors': 'GSW', 'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND',
    'LA Clippers': 'LAC', 'Los Angeles Lakers': 'LAL', 'Memphis Grizzlies': 'MEM',
    'Miami Heat': 'MIA', 'Milwaukee Bucks': 'MIL', 'Minnesota Timberwolves': 'MIN',
    'New Orleans Pelicans': 'NOP', 'New York Knicks': 'NYK', 'Oklahoma City Thunder': 'OKC',
    'Orlando Magic': 'ORL', 'Philadelphia 76ers': 'PHI', 'Phoenix Suns': 'PHX',
    'Portland Trail Blazers': 'POR', 'Sacramento Kings': 'SAC', 'San Antonio Spurs': 'SAS',
    'Toronto Raptors': 'TOR', 'Utah Jazz': 'UTA', 'Washington Wizards': 'WAS'
}

_team_id_lookup = None

def _get_team_by_id_lookup():
    global _team_id_lookup
    if _team_id_lookup is None:
        print("[helpers] Initializing team ID lookup cache...")
        all_teams = teams.get_teams() 
        _team_id_lookup = {team['id']: team for team in all_teams}
        print("[helpers] Team ID lookup cache created.")
    return _team_id_lookup

def find_team_by_id_replacement(team_id):
    lookup = _get_team_by_id_lookup()
    try:
        return lookup.get(int(team_id))
    except (ValueError, TypeError):
        return None

# -----------------------
# Rate limiting helper
# -----------------------
def rate_limit():
    """Small sleep to avoid hammering stats.nba.com"""
    time.sleep(1.5)


# -----------------------
# Schedule / scoreboard
# -----------------------
def get_upcoming_games(days=2):
    games_list = []
    today = datetime.now()

    for offset in range(days):
        d = today + timedelta(days=offset)
        date_str = d.strftime("%Y-%m-%d")
        print(f"[helpers] Fetching scoreboard for {date_str}...")
        
        # --- USE RETRY WRAPPER ---
        sb = _nba_api_request_wrapper(
            lambda: scoreboardv2.ScoreboardV2(
                game_date=date_str,
                timeout=60,
                headers=HEADERS 
            ),
            f"ScoreboardV2({date_str})"
        )
        
        if sb is None:
            print(f"[helpers][FATAL] Skipping day {date_str} after all retries.")
            continue
        # --- END WRAPPER ---
            
        gh = sb.game_header.get_data_frame() 
        
        if gh is None or gh.empty:
            print(f"[helpers] No games found on {date_str}")
            continue

        for _, row in gh.iterrows():
            try:
                home_obj = find_team_by_id_replacement(int(row['HOME_TEAM_ID']))
                away_obj = find_team_by_id_replacement(int(row['VISITOR_TEAM_ID']))
            except Exception as e:
                print(f"[helpers][WARN] find_team_by_id_replacement failed: {e}")
                continue

            if not home_obj or not away_obj:
                print(f"[helpers][WARN] Could not find team objects for game {row.get('GAME_ID')}")
                continue

            games_list.append({
                "game_id": row.get("GAME_ID"),
                "game_date": date_str,
                "home": home_obj.get("abbreviation"),
                "away": away_obj.get("abbreviation"),
                "home_team_name": home_obj.get("full_name"),
                "away_team_name": away_obj.get("full_name"),
                "game_description": f"{away_obj.get('abbreviation')} @ {home_obj.get('abbreviation')}"
            })

    print(f"[helpers] Found {len(games_list)} upcoming games.")
    return games_list


# -----------------------
# Team stats
# -----------------------
def get_team_stats(season="2025-26"):
    print("[helpers] Fetching team stats...")
    
    # --- USE RETRY WRAPPER ---
    stats = _nba_api_request_wrapper(
        lambda: leaguedashteamstats.LeagueDashTeamStats(
            season=season, 
            measure_type_detailed_defense="Advanced",
            timeout=60,
            headers=HEADERS
        ),
        f"LeagueDashTeamStats({season})"
    )
    
    if stats is None:
        return pd.DataFrame()
    # --- END WRAPPER ---
    
    df = stats.league_dash_team_stats.get_data_frame() 
    if df is None:
        return pd.DataFrame()
    return df.copy()


# -----------------------
# Players / rosters
# -----------------------
def get_all_active_players():
    print("[helpers] Fetching all active players...")
    rate_limit() # This one is static, no headers needed
    try:
        plist = players.get_players()
        df = pd.DataFrame(plist)
        active_df = df[df['is_active'] == True].copy()
        return active_df
    except Exception as e:
        print(f"[helpers][ERROR] get_all_active_players failed: {e}")
        return pd.DataFrame()


def get_team_roster(team_abbrev, season="2025-26"):
    print(f"[helpers] Fetching roster for {team_abbrev}...")
    try:
        team_obj = teams.find_team_by_abbreviation(team_abbrev)
        if not team_obj:
            print(f"[helpers][WARN] team not found for abbrev {team_abbrev}")
            return []
        team_id = team_obj["id"]
        
        # --- USE RETRY WRAPPER ---
        roster = _nba_api_request_wrapper(
            lambda: commonteamroster.CommonTeamRoster(
                team_id=team_id, 
                season=season,
                timeout=60,
                headers=HEADERS
            ),
            f"CommonTeamRoster({team_abbrev})"
        )
        
        if roster is None:
            return []
        # --- END WRAPPER ---
        
        rdf = roster.common_team_roster.get_data_frame()
        
        rdf = rdf.copy()
        rdf["id"] = rdf["PLAYER_ID"]
        rdf["full_name"] = rdf["PLAYER"]
        return rdf[["id", "full_name"]].to_dict("records")
    except Exception as e:
        print(f"[helpers][ERROR] get_team_roster failed for {team_abbrev}: {e}")
        return []


# -----------------------
# Player logs
# -----------------------
def get_player_game_logs(player_id, season="2025-26"):
    print(f"[helpers] Fetching game logs for player {player_id}, season {season}...")
    
    # --- USE RETRY WRAPPER ---
    logs = _nba_api_request_wrapper(
        lambda: playergamelog.PlayerGameLog(
            player_id=player_id, 
            season=season,
            timeout=60,
            headers=HEADERS
        ),
        f"PlayerGameLog({player_id}, {season})"
    )
    
    if logs is None:
        return None
    # --- END WRAPPER ---

    df = logs.player_game_log.get_data_frame() 
    if df is None or df.empty:
        print(f"[helpers][INFO] No game logs found for player {player_id} season {season}")
        return None
    return df.copy()


def get_player_position(player_name):
    print(f"[helpers] Fetching position for {player_name}...")
    rate_limit()
    try:
        candidates = players.find_players_by_full_name(player_name)
        if not candidates:
            return "N/A"
        pid = candidates[0]["id"]
        
        # --- USE RETRY WRAPPER ---
        info = _nba_api_request_wrapper(
            lambda: commonplayerinfo.CommonPlayerInfo(
                player_id=pid,
                timeout=60,
                headers=HEADERS
            ),
            f"CommonPlayerInfo({player_name})"
        )
        
        if info is None:
            return "N/A"
        # --- END WRAPPER ---
        
        df = info.common_player_info.get_data_frame()
        if "POSITION" in df.columns:
            return df["POSITION"].values[0]
        return "N/A"
    except Exception:
        return "N/A"

def get_head_to_head_history(all_player_logs_df, opponent_abbrev):
    print(f"[helpers] Filtering H2H logs vs {opponent_abbrev}...")
    try:
        if all_player_logs_df is None or all_player_logs_df.empty:
            return pd.DataFrame()
        
        if "MATCHUP" in all_player_logs_df.columns:
            filtered = all_player_logs_df[
                all_player_logs_df["MATCHUP"].str.contains(opponent_abbrev, na=False)
            ].copy()
            return filtered
        else:
            return pd.DataFrame()
    except Exception as e:
        print(f"[helpers][ERROR] get_head_to_head_history (filtering) failed: {e}")
        return pd.DataFrame()


# -----------------------
# DVP scraping
# -----------------------
def scrape_dvp_stats():
    # This scrapes a different website, so it doesn't need the NBA headers
    url = "https://hashtagbasketball.com/nba-defense-vs-position"
    print("[helpers] Scraping DVP stats...")
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code != 200:
            print(f"[helpers][WARN] DVP scrape returned {resp.status_code}")
            return {}
        # ... (rest of DVP scraping is unchanged) ...
        soup = BeautifulSoup(resp.content, "html.parser")
        position_ids = {
            "PG": "ContentPlaceHolder1_GridViewDVP",
            "SG": "ContentPlaceHolder1_GridViewDVP_SG",
            "SF": "ContentPlaceHolder1_GridViewDVP_SF",
            "PF": "ContentPlaceHolder1_GridViewDVP_PF",
            "C":  "ContentPlaceHolder1_GridViewDVP_C",
        }
        dvp_data = {}
        for pos, pid in position_ids.items():
            table = soup.find("table", id=pid)
            if not table:
                continue
            rows = table.find_all("tr")
            headers = [th.get_text(strip=True) for th in rows[0].find_all("th")]
            pos_map = {}
            for row in rows[1:]:
                cols = row.find_all("td")
                if not cols: continue
                row_data = {headers[i]: cols[i].get_text(strip=True) for i in range(len(cols))}
                team_name = row_data.get("TEAM")
                team_abbrev = TEAM_NAME_TO_ABBREV.get(team_name)
                if not team_abbrev:
                    continue
                stats = {}
                for k, v in row_data.items():
                    if k == "TEAM": continue
                    try:
                        stats[k] = float(v) if "." in v else int(v)
                    except Exception:
                        stats[k] = 0
                pos_map[team_abbrev] = stats
            dvp_data[pos] = pos_map
        print("[helpers] DVP scraping complete.")
        return dvp_data
    except Exception as e:
        print(f"[helpers][ERROR] DVP scrape failed: {e}")
        return {}


# -----------------------
# Odds API wrappers (optional)
# -----------------------
def fetch_all_odds_events(api_key):
    if not api_key:
        return []
    try:
        url = "https://api.the-odds-api.com/v4/sports/basketball_nba/events"
        r = requests.get(url, params={"apiKey": api_key}, timeout=8)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[helpers][WARN] odds events returned {r.status_code}")
            return []
    except Exception as e:
        print(f"[helpers][ERROR] fetch_all_odds_events failed: {e}")
        return []


def fetch_player_props_for_event(api_key, event_id):
    if not api_key or not event_id:
        return {}
    try:
        url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds"
        
        params = {
            "apiKey": api_key,
            "regions": "us",
            "bookmakers": "fanduel,draftkings",
            "markets": "player_points,player_assists,player_rebounds",
            "oddsFormat": "american",
        }
        r = requests.get(url, params=params, timeout=12)
        if r.status_code != 200:
            print(f"[helpers][WARN] odds props returned {r.status_code} for URL: {r.url}")
            return {}
        payload = r.json()
        processed = {}
        for bookmaker in payload.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                key = market.get("key", "")
                stat_type = None
                if "player_points" in key: stat_type = "pts"
                if "player_assists" in key: stat_type = "ast"
                if "player_rebounds" in key: stat_type = "reb"
                if stat_type:
                    for outcome in market.get("outcomes", []):
                        pname = outcome.get("description")
                        line = outcome.get("point")
                        if pname not in processed:
                            processed[pname] = {}
                        if stat_type not in processed[pname]:
                            processed[pname][stat_type] = {
                                "line": line,
                                "over_under": f"{outcome.get('name')} {line}"
                            }
        return processed
    except Exception as e:
        print(f"[helpers][ERROR] fetch_player_props_for_event failed: {e}")
        return {}