"""
Password Strength Checker — ported/inspired by ClatScope Mini (Clats97)
Rates password strength against 10k common passwords and multiple criteria.
"""
from __future__ import annotations

import re
from pathlib import Path

from .utils import console, print_section


_WORDLIST_PATH = Path(__file__).parent.parent / "data" / "passwords.txt"


def _load_wordlist() -> set[str]:
    try:
        with open(_WORDLIST_PATH, encoding="utf-8", errors="replace") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except FileNotFoundError:
        return set()


_WORDLIST: set[str] = _load_wordlist()


def check_password(password: str) -> dict:
    """
    Evaluate password strength.
    Returns a dict with score (0-100), rating, and list of issues/strengths.
    """
    issues: list[str] = []
    strengths: list[str] = []

    # ── Common password check ─────────────────────────────────────────────────
    if password.lower() in _WORDLIST:
        return {
            "score":  0,
            "rating": "Extremely Weak",
            "issues": ["Found in common password list — do not use this password"],
            "strengths": [],
        }
    # Check if any common word is a substring
    for word in _WORDLIST:
        if len(word) >= 5 and word in password.lower():
            issues.append(f"Contains common word/sequence: '{word}'")
            break

    score = 0

    # ── Length ────────────────────────────────────────────────────────────────
    length = len(password)
    if length < 8:
        issues.append("Too short (minimum 8 characters)")
    elif length >= 8:
        score += 15
        strengths.append("Minimum length met")
    if length >= 12:
        score += 10
        strengths.append("Good length (12+)")
    if length >= 16:
        score += 10
        strengths.append("Excellent length (16+)")
    if length >= 20:
        score += 5

    # ── Character variety ─────────────────────────────────────────────────────
    has_lower  = bool(re.search(r"[a-z]", password))
    has_upper  = bool(re.search(r"[A-Z]", password))
    has_digit  = bool(re.search(r"\d",    password))
    has_symbol = bool(re.search(r"[^a-zA-Z0-9]", password))

    if has_lower:
        score += 10; strengths.append("Contains lowercase letters")
    else:
        issues.append("No lowercase letters")
    if has_upper:
        score += 10; strengths.append("Contains uppercase letters")
    else:
        issues.append("No uppercase letters")
    if has_digit:
        score += 10; strengths.append("Contains digits")
    else:
        issues.append("No digits")
    if has_symbol:
        score += 15; strengths.append("Contains special characters")
    else:
        issues.append("No special characters")

    # Bonus for all four
    if has_lower and has_upper and has_digit and has_symbol:
        score += 10
        strengths.append("Uses all character classes")

    # ── Pattern penalties ─────────────────────────────────────────────────────
    if re.search(r"(.)\1{2,}", password):
        score -= 10
        issues.append("Repeated character pattern detected (e.g. aaa)")
    if re.search(r"(012|123|234|345|456|567|678|789|890|abc|bcd|cde)", password.lower()):
        score -= 10
        issues.append("Sequential pattern detected (e.g. 123, abc)")
    if re.search(r"(qwerty|asdf|zxcv|password|letmein|admin)", password.lower()):
        score -= 15
        issues.append("Keyboard pattern or obvious word detected")

    score = max(0, min(100, score))

    if score >= 80:
        rating = "Very Strong"
    elif score >= 60:
        rating = "Strong"
    elif score >= 40:
        rating = "Moderate"
    elif score >= 20:
        rating = "Weak"
    else:
        rating = "Very Weak"

    return {
        "score":     score,
        "rating":    rating,
        "issues":    issues,
        "strengths": strengths,
        "length":    length,
    }


def run(password: str) -> None:
    print_section("PASSWORD STRENGTH CHECKER")
    result = check_password(password)

    score  = result["score"]
    rating = result["rating"]

    colour = ("bold green" if score >= 80 else
              "green"      if score >= 60 else
              "yellow"     if score >= 40 else
              "orange3"    if score >= 20 else
              "bold red")

    # Score bar
    filled = int(score / 5)
    bar = "█" * filled + "░" * (20 - filled)

    console.print(f"\n  [{colour}]{bar}  {score}/100 — {rating}[/{colour}]\n")

    if result["strengths"]:
        console.print("  [bold green]Strengths:[/bold green]")
        for s in result["strengths"]:
            console.print(f"    [green][+][/green] {s}")

    if result["issues"]:
        console.print("\n  [bold red]Issues:[/bold red]")
        for i in result["issues"]:
            console.print(f"    [red][-][/red] {i}")

    console.print(f"\n  [dim]Length: {result['length']} characters | "
                  f"Wordlist: {len(_WORDLIST)} entries checked[/dim]")
