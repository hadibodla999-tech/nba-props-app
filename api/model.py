"""
api/model.py
Feature extraction, projection and hit-rate utilities.
Avoids SettingWithCopyWarning by using .copy() and .loc[:, ...].
"""

import pandas as pd
import numpy as np

# Defaults in case team stats are missing
DEFAULT_DEF_RATING = 110.0
DEFAULT_PACE = 100.0
DEFAULT_PTS_ALLOWED = 110.0

def _safe_mean(series):
    if series is None:
        return 0.0
    try:
        if hasattr(series, "empty") and series.empty:
            return 0.0
        return float(series.mean())
    except Exception:
        return 0.0


def calculate_season_averages(game_logs_df):
    if game_logs_df is None or game_logs_df.empty:
        return {'PTS': 0, 'AST': 0, 'REB': 0, 'FG3M': 0, 'MIN': 0, 'USG_PCT': 0, 'FGA': 0, 'FTA': 0, 'TOV': 0, 'FG3_PCT': 0}

    logs = game_logs_df.copy()

    # Ensure numeric columns exist and are numeric
    cols = ['FGA', 'FTA', 'TOV', 'MIN', 'PTS', 'AST', 'REB', 'FG3M', 'FG3_PCT']
    for col in cols:
        if col not in logs.columns:
            logs.loc[:, col] = 0
        logs.loc[:, col] = pd.to_numeric(logs[col], errors='coerce').fillna(0)

    # USG approximation
    logs.loc[:, 'USG_APPROX'] = (logs['FGA'] + 0.44 * logs['FTA'] + logs['TOV']) / logs['MIN']
    logs.loc[:, 'USG_APPROX'] = logs['USG_APPROX'].replace([np.inf, -np.inf], 0).fillna(0)

    return {
        'PTS': _safe_mean(logs['PTS']),
        'AST': _safe_mean(logs['AST']),
        'REB': _safe_mean(logs['REB']),
        'FG3M': _safe_mean(logs['FG3M']),
        'MIN': _safe_mean(logs['MIN']),
        'USG_PCT': _safe_mean(logs['USG_APPROX']),
        'FGA': _safe_mean(logs['FGA']),
        'FTA': _safe_mean(logs['FTA']),
        'TOV': _safe_mean(logs['TOV']),
        'FG3_PCT': _safe_mean(logs['FG3_PCT'])
    }


def calculate_recent_form(game_logs_df, last_n=10):
    if game_logs_df is None or game_logs_df.empty:
        return {f'PTS_L{last_n}': 0, f'AST_L{last_n}': 0, f'REB_L{last_n}': 0, f'FG3M_L{last_n}': 0, f'MIN_L{last_n}': 0, f'USG_L{last_n}': 0}

    recent = game_logs_df.head(last_n).copy()

    cols = ['FGA', 'FTA', 'TOV', 'MIN', 'PTS', 'AST', 'REB', 'FG3M']
    for col in cols:
        if col not in recent.columns:
            recent.loc[:, col] = 0
        recent.loc[:, col] = pd.to_numeric(recent[col], errors='coerce').fillna(0)

    recent.loc[:, 'USG_APPROX'] = (recent['FGA'] + 0.44 * recent['FTA'] + recent['TOV']) / recent['MIN']
    recent.loc[:, 'USG_APPROX'] = recent['USG_APPROX'].replace([np.inf, -np.inf], 0).fillna(0)

    return {
        f'PTS_L{last_n}': _safe_mean(recent['PTS']),
        f'AST_L{last_n}': _safe_mean(recent['AST']),
        f'REB_L{last_n}': _safe_mean(recent['REB']),
        f'FG3M_L{last_n}': _safe_mean(recent['FG3M']),
        f'MIN_L{last_n}': _safe_mean(recent['MIN']),
        f'USG_L{last_n}': _safe_mean(recent['USG_APPROX'])
    }


def get_opponent_context(team_stats_df, opponent_abbrev):
    if team_stats_df is None or team_stats_df.empty:
        return {'DEF_RATING': DEFAULT_DEF_RATING, 'PACE': DEFAULT_PACE, 'PTS_ALLOWED': DEFAULT_PTS_ALLOWED}

    # older/newer versions may have different column names; check both
    if 'TEAM_ABBREVIATION' not in team_stats_df.columns and 'TEAM_ABBREV' not in team_stats_df.columns:
        return {'DEF_RATING': DEFAULT_DEF_RATING, 'PACE': DEFAULT_PACE, 'PTS_ALLOWED': DEFAULT_PTS_ALLOWED}

    col_name = 'TEAM_ABBREVIATION' if 'TEAM_ABBREVIATION' in team_stats_df.columns else 'TEAM_ABBREV'
    opp_df = team_stats_df[team_stats_df[col_name] == opponent_abbrev]
    if opp_df.empty:
        return {'DEF_RATING': DEFAULT_DEF_RATING, 'PACE': DEFAULT_PACE, 'PTS_ALLOWED': DEFAULT_PTS_ALLOWED}

    def_rating = opp_df['E_DEF_RATING'].values[0] if 'E_DEF_RATING' in opp_df.columns else DEFAULT_DEF_RATING
    pace = opp_df['E_PACE'].values[0] if 'E_PACE' in opp_df.columns else DEFAULT_PACE
    pts_allowed = (def_rating * pace) / 100 if pace else DEFAULT_PTS_ALLOWED

    return {'DEF_RATING': float(def_rating), 'PACE': float(pace), 'PTS_ALLOWED': float(pts_allowed)}


def build_enhanced_feature_vector(player_game_logs, opponent_abbrev, team_abbrev, player_pos, dvp_data, head_to_head_games=None, team_stats_df=None):
    features = {}
    try:
        features.update(calculate_season_averages(player_game_logs))
        features.update(calculate_recent_form(player_game_logs, last_n=10))
        features.update(calculate_recent_form(player_game_logs, last_n=5))

        opp_context = get_opponent_context(team_stats_df, opponent_abbrev)
        features.update(opp_context)

        # DVP rank if available
        try:
            dvp = dvp_data.get(player_pos, {}).get(opponent_abbrev, {}) if dvp_data else {}
            features['DVP_RANK'] = dvp.get('Rank', 15) if dvp else 15
        except Exception:
            features['DVP_RANK'] = 15

    except Exception as e:
        print(f"[model][ERROR] build_enhanced_feature_vector: {e}")

    return features


def predict_weighted_average(features, key):
    recent = features.get(f'{key}_L5', 0.0)
    recent10 = features.get(f'{key}_L10', 0.0)
    season = features.get(key, 0.0)
    try:
        return float(0.6 * recent + 0.25 * recent10 + 0.15 * season)
    except Exception:
        return 0.0


class PlayerPropModel:
    stat_types = ['pts', 'ast', 'reb', 'PRA']

    def predict(self, features_dict, stat_type):
        try:
            if stat_type == 'pts':
                return predict_weighted_average(features_dict, 'PTS')
            if stat_type == 'ast':
                return predict_weighted_average(features_dict, 'AST')
            if stat_type == 'reb':
                return predict_weighted_average(features_dict, 'REB')
            if stat_type == 'PRA':
                pts = predict_weighted_average(features_dict, 'PTS')
                reb = predict_weighted_average(features_dict, 'REB')
                ast = predict_weighted_average(features_dict, 'AST')
                return pts + reb + ast
            return 0.0
        except Exception as e:
            print(f"[model][ERROR] prediction error: {e}")
            return 0.0


def calculate_hit_rates(game_logs_df, stat, book_line):
    try:
        if game_logs_df is None or game_logs_df.empty or book_line is None:
            return {'L5': 0, 'L10': 0, 'Season': 0}
        logs = game_logs_df.copy()
        col_map = {'pts': 'PTS', 'ast': 'AST', 'reb': 'REB'}
        col = col_map.get(stat)
        if not col or col not in logs.columns:
            return {'L5': 0, 'L10': 0, 'Season': 0}
        series = pd.to_numeric(logs[col], errors='coerce').fillna(0)
        def hr(n):
            s = series.head(n)
            if s.empty: return 0
            return int((s > book_line).sum() / len(s) * 100)
        return {'L5': hr(5), 'L10': hr(10), 'Season': hr(len(series))}
    except Exception as e:
        print(f"[model][ERROR] calculate_hit_rates: {e}")
        return {'L5': 0, 'L10': 0, 'Season': 0}
