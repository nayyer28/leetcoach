"""Backward-compatible Telegram bot import path."""

from leetcoach.app.interface.bot import handlers as _handlers
from leetcoach.app.interface.bot.handlers import *  # noqa: F403

start_quiz = _handlers.start_quiz
list_recent_problems = _handlers.list_recent_problems
_interrupt_quiz_if_needed = _handlers._interrupt_quiz_if_needed
_reply_long_text = _handlers._reply_long_text
_canonical_pattern_label = _handlers._canonical_pattern_label
_chunk_text = _handlers._chunk_text
_difficulty_inline_markup = _handlers._difficulty_inline_markup
_extract_problem_slug = _handlers._extract_problem_slug
_format_timestamp = _handlers._format_timestamp
_is_user_allowed = _handlers._is_user_allowed
_leetcode_url = _handlers._leetcode_url
_neetcode_url = _handlers._neetcode_url
_normalize_difficulty_input = _handlers._normalize_difficulty_input
_normalize_solved_at = _handlers._normalize_solved_at
_parse_log_show_limit = _handlers._parse_log_show_limit
_pattern_inline_markup = _handlers._pattern_inline_markup
_render_due = _handlers._render_due
_render_problem_detail = _handlers._render_problem_detail
_render_problem_rows = _handlers._render_problem_rows
_render_quiz_question = _handlers._render_quiz_question
_render_quiz_reveal = _handlers._render_quiz_reveal
_unknown_command_help_text = _handlers._unknown_command_help_text
_unknown_text_help_text = _handlers._unknown_text_help_text


async def log_command(update, context):
    _handlers._interrupt_quiz_if_needed = _interrupt_quiz_if_needed
    _handlers.list_recent_problems = list_recent_problems
    _handlers._reply_long_text = _reply_long_text
    return await _handlers.log_command(update, context)


async def quiz_command(update, context):
    _handlers.start_quiz = start_quiz
    return await _handlers.quiz_command(update, context)
