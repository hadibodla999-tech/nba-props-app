# THIS IS THE NEW, COMPLETE api/helpers.py FILE
# Delete all old code in this file and replace it with this.

import os
import requests
import logging
import sys
from datetime import datetime

# --- Setup ---
# Set up a simple logger to print messages
logging.basicConfig(
    level=logging.INFO,
    format="[helpers] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- API-BASKETBALL CONFIGURATION ---
# We get the API key from the GitHub Secrets (via os.environ)
API_KEY = os.environ.get("RAPIDAPI_KEY")
API_HOST = "api-basketball.p.rapidapi.com"
BASE_URL = "https://v1.basketball.api-sports.io"

# We must send these headers with every single request
HEADERS = {
    "x-rapidapi-host": API_HOST,
    "x-rapidapi-key": API_KEY
}

# --- CONSTANTS ---
# The League ID for "NBA" in this API is 12
# The Season is 2025-2026 (based on your original bot log)
NBA_LEAGUE_ID = 12
CURRENT_SEASON = "2025-2026"


def _api_request_wrapper(endpoint, params):
    """
    A robust wrapper for making all requests to API-Basketball.
    This will handle errors and check our remaining quota.
    """
    if not API_KEY:
        logger.error("RAPIDAPI_KEY is not set. Bot cannot run.")
        return None

    try:
        url = f"https{BASE_URL}/{endpoint}"
        # This is the actual API call
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        
        # Raise an error if the request failed (e.g., 404, 500)
        response.raise_for_status() 
        
        data = response.json()
        
        # Check if the API itself sent an error message
        if data.get("errors"):
            logger.error(f"API Error for {endpoint}: {data['errors']}")
            return None
            
        # Check our remaining requests for the day
        remaining = response.headers.get('x-ratelimit-requests-remaining')
        if remaining:
            logger.info(f"API requests remaining today: {remaining}")
            
        return data.get("response", [])
        
    except requests.exceptions.Timeout:
        logger.error(f"Request Timed Out for {endpoint}.")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error for {endpoint}: {e.response.status_code} {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch {endpoint}: {e}")
        return None

# -----------------------
# REWRITTEN FUNCTIONS
# -----------------------

def get_upcoming_games(days=1):
    """
    Gets upcoming games for today.
    This replaces the old 'ScoreboardV2' function.
    This uses 1 API Request.
    """
    logger.info(f"Fetching scoreboard for today...")
    
    # Get today's date in YYYY-MM-DD format
    # (Note: API-Sports may be 1 day behind, so you might
    # want to fetch for `yesterday` if you run this in the morning)
    today_str = (datetime.now()).strftime("%Y-%m-%d")
    
    params = {
        "league": NBA_LEAGUE_ID,
        "season": CURRENT_SEASON,
        "date": today_str
    }
    
    # Call the API
    games = _api_request_wrapper("games", params)
    
    if games is None:
        logger.error("Failed to fetch games.")
        return []
    
    if not games:
        logger.info(f"No games found on {today_str}")
        return []

    # Format the data to match our old structure
    games_list = []
    for game in games:
        game_data = {
            "game_id": game["id"],
            "game_date": today_str,
            "home": game["teams"]["home"]["code"],
            "away": game["teams"]["visitors"]["code"],
            "home_team_name": game["teams"]["home"]["name"],
            "away_team_name": game["teams"]["visitors"]["name"],
            "game_description": f"{game['teams']['visitors']['code']} @ {game['teams']['home']['code']}",
            "player_stats": [] # We will fill this in the main script
        }
        games_list.append(game_data)

    logger.info(f"Found {len(games_list)} upcoming games.")
    return games_list


def get_player_stats_for_game(game_id):
    """
    Gets all player stats for a single game.
    This replaces the old 'playergamelog' function.
    This uses 1 API Request *per game*.
    """
    logger.info(f"Fetching player stats for game {game_id}...")
    
    params = {"league": NBA_LEAGUE_ID, "id": game_id}
    
    data = _api_request_wrapper("games/statistics", params)
    
    if not data:
        logger.warning(f"No player stats found for game {game_id}")
        return []
        
    # The API returns stats for two teams. We need to combine them.
    all_player_stats = []
    
    # The response is a list with two items: [team_1_stats, team_2_stats]
    for team_stats in data:
        team_name = team_stats["team"]["name"]
        for player_stat in team_stats["statistics"]:
            player_info = player_stat.get("player", {})
            
            # Format the data to be easy to save in Firebase
            formatted_stat = {
                "player_id": player_info.get("id"),
                "player_name": f"{player_info.get('firstname')} {player_info.get('lastname')}",
                "team_name": team_name,
                "min": player_stat.get("min"),
                "pts": player_stat.get("points"),
                "reb": player_stat.get("totReb"),
                "ast": player_stat.get("assists"),
                "stl": player_stat.get("steals"),
                "blk": player_stat.get("blocks"),
                "turnovers": player_stat.get("turnovers"),
                "fgm": player_stat.get("fgm"),
                "fga": player_stat.get("fga"),
                "tpm": player_stat.get("tpm"), # 3-pointers made
                "tpa": player_stat.get("tpa"), # 3-pointers attempted
                "ftm": player_stat.get("ftm"), # Free throws made
                "fta": player_stat.get("fta"), # Free throws attempted
            }
            all_player_stats.append(formatted_stat)

    logger.info(f"Found stats for {len(all_player_stats)} players in game {game_id}.")
    return all_player_stats
