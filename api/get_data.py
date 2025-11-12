# THIS IS THE NEW, COMPLETE api/get_data.py FILE
# Delete all old code in this file and replace it with this.

import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# Add api directory to path to import helpers
# This allows us to run `python api/get_data.py` from the root folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import our new helper functions
import helpers

# --- Setup ---
# This makes our print messages clean
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- Firebase Initialization ---
def initialize_firebase():
    """
    Initializes the Firebase Admin SDK using the GitHub Secret.
    """
    logger.info("Initializing Firebase Admin...")
    try:
        # 1. Get the Firebase key from GitHub Secrets
        cred_json_string = os.environ.get("FIREBASE_ADMIN_KEY")
        if not cred_json_string:
            logger.error("FIREBASE_ADMIN_KEY not found in environment.")
            return None
        
        # 2. Convert the string secret back into a dictionary
        # We use eval() here because GitHub secrets store it as a string
        cred_dict = eval(cred_json_string) 
        cred = credentials.Certificate(cred_dict)
        
        # 3. Check if the app is already initialized to avoid errors
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            
        logger.info("Firebase Admin initialized.")
        return firestore.client()
        
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        return None

# --- Main Bot Logic ---
def main():
    logger.info("--- BOT SCRIPT START (Using API-Basketball) ---")
    
    # 1. Initialize Firebase
    db = initialize_firebase()
    if db is None:
        sys.exit(1) # Exit with an error

    # 2. Get Today's Games
    # This is our first API call (1 request)
    games = helpers.get_upcoming_games(days=1)
    
    if not games:
        logger.info("No games scheduled for today. Bot finished.")
        return

    logger.info(f"Found {len(games)} games. Fetching player stats for each...")

    all_games_data = []

    # 3. Loop through each game and get player stats
    for game in games:
        game_id = game["game_id"]
        
        # This is our loop of API calls (1 request *per game*)
        player_stats = helpers.get_player_stats_for_game(game_id)
        
        # Add the player stats to our game object
        game["player_stats"] = player_stats
        all_games_data.append(game)

    # 4. Save all data to Firebase
    try:
        # Create a single document for today's data
        today_str = datetime.now().strftime("%Y-%m-%d")
        doc_ref = db.collection("nba_games").document(today_str)
        
        # We'll save a big object that contains all of today's games
        doc_ref.set({
            "games": all_games_data,
            "last_updated": firestore.SERVER_TIMESTAMP
        })
        
        logger.info(f"Successfully saved all data to Firestore document: {today_str}")
        
    except Exception as e:
        logger.error(f"Failed to save data to Firestore: {e}")

    logger.info("--- BOT SCRIPT END ---")

if __name__ == "__main__":
    # This allows you to test the script locally
    # It will load secrets from a file named ".env"
    load_dotenv()
    main()
