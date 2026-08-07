from models.activity import Activity
from discord import ActivityType
from datetime import datetime
from loguru import logger
import re

# timeline symbols
TIMELINE_SYMBOL = "-"
TIMELINE_POINTER = "●"
TIMELINE_NUM_SEGMENTS = 20

# Junk keywords patterns
VIDEO_JUNK_PATTERN = r'official video|official music video|music video|lyric video|audio|remastered|deluxe edition|4k|hd|60fps|musical artist|official lyric video|Official Video 4K'
GAME_JUNK_PATTERN = r'^Playing\s+on\s+[\w\d_-]+\s*-\s*|^Playing\s+on\s+[\w\d_-]+'

def get_message_text(act: Activity):
    prefix = get_prefix(act.type)

    if (act.end_time):
        return format_tl_act(act)
    else:
        return format_act(act, prefix)

def get_prefix(type: ActivityType):
    prefix = "⏱️"
    if type == ActivityType.playing:
        prefix = "⏱️"
    if type == ActivityType.watching:
        prefix = "⏱️"
    if type == ActivityType.listening:
        prefix = "⏱️"
    return prefix

def clean_text(text: str, is_game: bool = False) -> str:
    # Removes video junk words, game RPC host device info, surrounding brackets, and converts Season/Episode formats.
    if not text:
        return ""
    
    # 1. Strip newlines to prevent forced multi-line text
    text = text.replace('\r', '').replace('\n', ' ')

    # 2. Strip game device/platform prefixes ("Playing on - ")
    text = re.sub(GAME_JUNK_PATTERN, '', text, flags=re.IGNORECASE).strip()

    # Skip video/music junk pattern stripping if this activity is a Game
    if not is_game:
        # 3. Convert Season X Episode Y -> (SX-EY)
        season_pattern = r'[Ss]eason\s*(\d+)[,\s\-_]+[Ee]pisode\s*(\d+)'
        def season_repl(match):
            s_num, e_num = int(match.group(1)), int(match.group(2))
            return f"(S{s_num:02d}-E{e_num:02d})"
        
        text = re.sub(season_pattern, season_repl, text)

        # 4. Strip brackets/parentheses containing video junk keywords
        text = re.sub(fr'\s*[\(\[]\s*(?:{VIDEO_JUNK_PATTERN})\s*[\)\]]', '', text, flags=re.IGNORECASE)
        
        # 5. Strip standalone video junk keywords
        text = re.sub(fr'\s*(?:{VIDEO_JUNK_PATTERN})', '', text, flags=re.IGNORECASE)

    return text.strip()

def build_content_lines(act: Activity) -> list:
    
    is_game = (act.type == ActivityType.playing)

    details = clean_text(act.details, is_game=is_game) if act.details else ""
    state = clean_text(act.state, is_game=is_game) if act.state else ""
    large_text = clean_text(act.large_text, is_game=is_game) if act.large_text else ""

    lines = []
    full_title = ""

    # Check raw act.state for ratings
    raw_state = str(act.state or "").strip()
    is_rating = bool(re.search(r'\d+(?:\.\d+)?', raw_state) and ("⭐" in raw_state or "star" in raw_state.lower() or len(raw_state) <= 6))

    # 1. TV Show format
    EPISODE_REGEX = r'(S\d+E\d+)(?:\s*-\s*(.*))?'
    match = re.search(EPISODE_REGEX, raw_state, re.IGNORECASE)

    if match and details:
        episode_code = match.group(1).upper()
        full_title = f"<b>{details}</b> - {episode_code}"

    # 2. Movie with Rating
    elif details and is_rating:
        # Puts movie name only
        full_title = f"<b>{details}</b>" if raw_state else f"<b>{details}</b>"

    # 3. Details already contains ' - ' (e.g. YouTube Video: "Artist - Title")
    elif details and ' - ' in details:
        full_title = f"<b>{details}</b>"

    # 4. Music / Spotify / YouTube Music (details="Title", state="Artist")
    elif details and state and state.lower() not in details.lower():
        full_title = f"<b>{state} - {details}</b>"

    # 5. Single field fallback
    elif details:
        full_title = f"<b>{details}</b>"
    elif state:
        full_title = f"<b>{state}</b>"

    if full_title:
        lines.append(full_title)

    # Secondary app / URL info
    if large_text and large_text.lower() not in ["youtube", "youtube music", "spotify", "kodi", "trakt", "trakt.tv"]:
        if not any(large_text.lower() in line.lower() for line in lines):
            if act.large_url:
                lines.append(f"<a href='{act.large_url}'>&gt; {large_text}</a>")
            else:
                lines.append(f"{large_text}")

    return lines

def format_act(act: Activity, time_prefix: str) -> str:
    result = build_content_lines(act)
    result.append(f"\r\n{time_prefix} {act.get_elapsed_time()}")
    return "\n".join(result)

def format_tl_act(act: Activity) -> str:
    parts = []
    
    for _ in range(TIMELINE_NUM_SEGMENTS):
        parts.append(TIMELINE_SYMBOL)
    
    now = datetime.now(act.start_time.tzinfo) if act.start_time else datetime.now()
    
    if act.track_length and act.start_time:
        elapsed = now - act.start_time

        # Cap elapsed time so it doesn't overflow past track duration
        if elapsed > act.track_length:
            elapsed = act.track_length

        # Safely calculate segment position
        segment_duration = act.track_length / TIMELINE_NUM_SEGMENTS
        if segment_duration.total_seconds() > 0:
            pointer_index = int(elapsed / segment_duration)
            
            # Clamp index between 0 and TIMELINE_NUM_SEGMENTS - 1
            pointer_index = max(0, min(pointer_index, TIMELINE_NUM_SEGMENTS - 1))
            parts[pointer_index] = TIMELINE_POINTER

        # Format elapsed string cleanly capped at track duration
        total_sec = int(elapsed.total_seconds())
        m, s = divmod(total_sec, 60)
        h, m = divmod(m, 60)
        elapsed_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    else:
        elapsed_str = act.get_elapsed_time()

    timeline = "".join(parts)
    prefix = get_prefix(act.type)

    # Get text lines
    result = build_content_lines(act)

    progress = f"{elapsed_str}{timeline}{act.get_track_length()}{prefix}"
    result.append(f"\n{progress}")

    return "\n\n".join(result)
