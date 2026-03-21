from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from leetcoach.app.application.shared.patterns import ROADMAP_PATTERN_LEVELS, normalize_pattern_key


def pattern_option_rows() -> list[list[str]]:
    labels = [
        label
        for _, label in sorted(
            ROADMAP_PATTERN_LEVELS.values(), key=lambda item: (item[0], item[1].lower())
        )
    ]
    return [labels[idx : idx + 2] for idx in range(0, len(labels), 2)]


def difficulty_inline_markup(
    *,
    difficulty_options: list[list[str]],
    callback_prefix: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    label,
                    callback_data=f"{callback_prefix}{label.lower()}",
                )
                for label in difficulty_options[0]
            ]
        ]
    )


def pattern_inline_markup(*, callback_prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    label,
                    callback_data=f"{callback_prefix}{normalize_pattern_key(label)}",
                )
                for label in row
            ]
            for row in pattern_option_rows()
        ]
    )
