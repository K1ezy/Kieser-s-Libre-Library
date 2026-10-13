from .id_card import ROLE_CONFIGS, get_user_initials, render_pvc_id_card
from .media_modals import open_avatar_modal, open_cover_modal
from .stats_badges import render_profile_stats

PROGRAM_OPTIONS = ["BSCS", "BSIT", "BSED", "BEED", "BSBA", "BSHM", "Crim", "Nursing", "GENERAL"]
YEAR_LEVEL_OPTIONS = ["1st Year", "2nd Year", "3rd Year", "4th Year", "Graduate"]

__all__ = [
    'ROLE_CONFIGS',
    'get_user_initials',
    'render_pvc_id_card',
    'open_avatar_modal',
    'open_cover_modal',
    'render_profile_stats',
    'PROGRAM_OPTIONS',
    'YEAR_LEVEL_OPTIONS',
]
