"""Locale configuration - generate and set UTF-8 locale."""

import logging

from machine_setup.utils import run, sudo_prefix

logger = logging.getLogger("machine_setup")

LOCALE = "en_US.UTF-8"


def is_locale_generated(locale: str) -> bool:
    """Check if a locale is already generated."""
    result = run(["locale", "-a"], check=True, capture=True)
    return locale.replace("UTF-8", "utf8") in result.stdout


def generate_locale(locale: str) -> None:
    """Generate specified locale using locale-gen."""
    logger.info("Generating locale: %s", locale)
    sudo = sudo_prefix()

    sed_escape = locale.replace(".", "\\.")

    run(
        [
            *sudo,
            "sed",
            "-i",
            "-e",
            f"s/^# *{sed_escape}/{locale}/",
            "/etc/locale.gen",
        ]
    )
    run([*sudo, "locale-gen"])
    logger.info("Locale generation complete")


def setup_locale() -> None:
    """Configure UTF-8 locale."""
    if is_locale_generated(LOCALE):
        logger.info("Locale %s already generated", LOCALE)
        return

    locale_gen = run(["which", "locale-gen"], check=False, capture=True)
    if locale_gen.returncode != 0:
        logger.warning("locale-gen not found; skipping locale configuration")
        return

    generate_locale(LOCALE)
