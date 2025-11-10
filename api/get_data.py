"""
api/get_data.py
THIS IS NOW THE BOT SCRIPT. IT IS NOT A FLASK SERVER.
It runs, fetches all data, and saves to Firestore.
"""

import os
import sys
import json
import time
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# make project root visible for imports
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

try:
    from api import helpers
    from api import model
except Exception:
    import helpers
    import model

# Load .env file for local development
print("[get_data] Loading .env file...")
load_dotenv()

# --- NEW: Firebase Admin Setup ---
def initialize_firebase():
    """
    Initializes the Firebase Admin SDK.
    It reads the secret key from an environment variable.
    """
    print("[get_data] Initializing Firebase Admin...")
    try:
        # GitHub Actions will provide this as a JSON string
        cred_json = os.environ.get("FIREBASE_ADMIN_KEY")
        if not cred_json:
            print("[get_data][ERROR] FIREBASE_ADMIN_KEY env variable not set.")
            # Fallback for local dev: load from the file you uploaded
            # Ensure this file is in your .gitignore!
            local_key_path = "nba-props-app-57fec-firebase-adminsdk-fbsvc-cd74aaf81d.json"
            if os.path.exists(local_key_path):
                print("[get_data] Using local service account file.")
                cred = credentials.Certificate(local_key_path)
            else:
                raise Exception("Local key file not found and ENV var missing.")
        else:
            print("[get_data] Using service account from ENV variable.")
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)

        firebase_admin.initialize_app(cred)
        print("[get_data] Firebase Admin initialized.")
        return firestore.client()
    except Exception as e:
        print(f"[get_data][FATAL] Firebase Admin initialization failed: {e}")
        return None

# --- NEW: Firebase Write Function ---
def save_data_to_firestore(db, data):
    """
    Saves the complete player data array to the daily cache doc.
    """
    try:
        if not data:
            print("[get_data][WARN] No data to save. Skipping Firestore write.")
            return

        today = datetime.now()
        cache_key = today.strftime("%Y-%m-%d")
        
        # This matches the path your App.jsx is reading from
        doc_ref = db.collection("artifacts").document("default-app-id").collection("public/data/nba_props_cache").document(cache_key)
        
        print(f"[get_data] Saving {len(data)} player props to Firestore at: {doc_ref.path}")
        
        # Serialize data for Firestore
        payload = {
            "playerData": json.dumps(data),
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
        
        doc_ref.set(payload)
        print("[get_data] Save to Firestore complete.")
    except Exception as e:
        print(f"[get_data][ERROR] Failed to save to Firestore: {e}")

# --- Core Logic (Modified) ---

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", None)

def get_current_nba_season():
    now = datetime.now()
    if now.month >= 10:
        start_year = now.year
        end_year = str(now.year + 1)[-2:]
    else:
        start_year = now.year - 1
        end_year = str(now.year)[-2:]
    return f"{start_year}-{end_year}"

CURRENT_SEASON = get_current_nba_season()
prior_year_start = int(CURRENT_SEASON.split('-')[0]) - 1
prior_year_end = str(prior_year_start + 1)[-2:]
PRIOR_SEASON = f"{prior_year_start}-{prior_year_end}"

def get_real_player_data():
    start = datetime.now()
    print("[get_data] --- BOT SCRIPT START ---")
    print(f"[get_data] Using CURRENT_SEASON: {CURRENT_SEASON}")

    # STEP 1: fetch global data
    try:
        print("[get_data] STEP 1: Fetching upcoming games, players, DVP and team stats...")
        games = helpers.get_upcoming_games(days=2)
        if not games:
            print("[get_data][INFO] No upcoming games found -> returning []")
            return []
        all_players_df = helpers.get_all_active_players()
        dvp_data = helpers.scrape_dvp_stats()
        team_stats_df = helpers.get_team_stats(CURRENT_SEASON)
    except Exception as e:
        print(f"[get_data][ERROR] Step 1 failed: {e}")
        return {"error": f"Failed to fetch global data: {e}"}

    # STEP 2: odds events (optional)
    print("[get_data] STEP 2: Fetching odds events (optional)...")
    try:
        all_odds_events = helpers.fetch_all_odds_events(ODDS_API_KEY)
    except Exception as e:
        print(f"[get_data][WARN] Odds events fetch failed: {e}")
        all_odds_events = []

    # STEP 3: process games & players
    print(f"[get_data] STEP 3: Processing {len(games)} games...")
    prop_model = model.PlayerPropModel()
    results = []

    for i, game in enumerate(games):
        game_id = game.get("game_id")
        home = game.get("home")
        away = game.get("away")
        desc = game.get("game_description")
        gdate = game.get("game_date")
        print(f"[get_data] Processing game {i+1}/{len(games)}: {desc} ({game_id})")

        event_id = None
        for ev in all_odds_events:
            if ev.get("id") and (game.get("home_team_name") in (ev.get("home_team") or "") or game.get("away_team_name") in (ev.get("away_team") or "")):
                event_id = ev.get("id")
                break
        game_odds = {}
        if event_id:
            game_odds = helpers.fetch_player_props_for_event(ODDS_API_KEY, event_id)

        rosters = {}
        for t in (home, away):
            if not t or t == "N/A": continue
            try:
                rosters[t] = helpers.get_team_roster(t, season=CURRENT_SEASON)
            except Exception as e:
                print(f"[get_data][WARN] roster fetch failed for {t}: {e}")
                rosters[t] = []

        for team_abbrev, roster in rosters.items():
            opponent_abbrev = away if team_abbrev == home else home
            if not roster:
                print(f"[get_data][WARN] Empty roster for {team_abbrev}, skipping")
                continue

            for player in roster:
                player_id = player.get("id")
                player_name = player.get("full_name")
                print(f"[get_data]  Player {player_name} ({team_abbrev} vs {opponent_abbrev})")

                try:
                    logs_current = helpers.get_player_game_logs(player_id, CURRENT_SEASON)
                    logs_prior = helpers.get_player_game_logs(player_id, PRIOR_SEASON)

                    if logs_current is None and logs_prior is None:
                        print(f"[get_data]    No logs for {player_name} -> skip")
                        continue

                    frames = [df for df in [logs_current, logs_prior] if df is not None]
                    all_logs = pd.concat(frames, ignore_index=True).sort_values(by="GAME_DATE", ascending=False)
                    if all_logs.empty:
                        print(f"[get_data]    Combined logs empty for {player_name} -> skip")
                        continue

                    h2h = helpers.get_head_to_head_history(all_logs, opponent_abbrev)
                    pos = helpers.get_player_position(player_name)

                    features = model.build_enhanced_feature_vector(
                        player_game_logs=all_logs,
                        opponent_abbrev=opponent_abbrev,
                        team_abbrev=team_abbrev,
                        player_pos=pos,
                        dvp_data=dvp_data,
                        head_to_head_games=h2h,
                        team_stats_df=team_stats_df
                    )

                    for stat in prop_model.stat_types:
                        projection = prop_model.predict(features, stat)
                        if projection is None or projection == 0:
                            continue

                        book_line = None
                        ou_str = None
                        if player_name in game_odds:
                            cand = game_odds[player_name]
                            if stat == "pts" and cand.get("pts"):
                                book_line = cand["pts"]["line"]
                                ou_str = cand["pts"]["over_under"]
                            if stat == "ast" and cand.get("ast"):
                                book_line = cand["ast"]["line"]
                                ou_str = cand["ast"]["over_under"]
                            if stat == "reb" and cand.get("reb"):
                                book_line = cand["reb"]["line"]
                                ou_str = cand["reb"]["over_under"]

                        hit_rates = model.calculate_hit_rates(all_logs, stat, book_line)
                        pdata = {
                            "id": f"{player_id}-{stat}",
                            "gameId": game_id,
                            "gameDate": gdate,
                            "gameDescription": desc,
                            "playerName": player_name,
                            "team": team_abbrev,
                            "opponent": opponent_abbrev,
                            "stat": stat,
                            "projection": round(float(projection), 2),
                            "bookLine": book_line,
                            "overUnder": ou_str,
                            "isStarter": True,
                            "hitRate": {
                                "L5": hit_rates.get("L5", 0),
                                "L10": hit_rates.get("L10", 0),
                                "Season": hit_rates.get("Season", 0)
                            }
                        }
                        results.append(pdata)
                except Exception as e:
                    print(f"[get_data][ERROR] Failed processing player {player_name}: {e}")
                    continue
        
        # --- ROBUSTNESS FIX: COOL-DOWN PERIOD ---
        if i < len(games) - 1: # Don't sleep after the very last game
            print(f"[get_data] Game {i+1} complete. Cooling down for 15 seconds...")
            time.sleep(15)
        # --- END OF FIX ---

    end = datetime.now()
    dur = (end - start).total_seconds()
    print(f"[get_data] --- API REQUEST END (duration: {dur:.1f}s). Results: {len(results)} players")
    return results


# --- NEW: Main execution block ---
if __name__ == "__main__":
    # This is what the GitHub Action "bot" will run
    db = initialize_firebase()
    if db:
        player_data = get_real_player_data()
        save_data_to_firestore(db, player_data)
    else:
        print("[get_data][FATAL] Could not initialize Firebase. Exiting.")
        sys.exit(1)