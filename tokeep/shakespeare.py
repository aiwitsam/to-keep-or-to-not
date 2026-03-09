"""All Shakespeare-themed text for the backup TUI."""

import random

BANNERS = [
    "To keep, or not to keep — that is the question.",
    "All the world's a drive, and all the files merely players.",
    "Once more unto the drive, dear friends, once more!",
    "Some are born backed up, some achieve backups, and some have backups thrust upon them.",
    "We know what we have, but know not what we may lose.",
    "Though this be backup, yet there is a method in't.",
    "There is nothing either safe or lost, but syncing makes it so.",
    "Brevity is the soul of a good backup strategy.",
    "This above all: to thine own data be true.",
    "What's in a snapshot? That which we call a backup by any other name would restore as sweet.",
]

CONFIRMATIONS = {
    "backup": [
        "Thus is it preserved upon the sacred external tome!",
        "Sealed and synced — thy data sleeps soundly tonight.",
        "The quill hath copied the parchment. It is kept!",
    ],
    "verify": [
        "The audit is complete — all accounts are in order!",
        "Inspected and found worthy. The backup stands true!",
        "Every byte accounted for. The ledger is balanced.",
    ],
    "prune": [
        "The old growth is cleared — room for new harvests!",
        "Farewell, aged snapshots. Your service is honored.",
        "Pruned with care — only the worthy remain.",
    ],
    "schedule": [
        "The clockwork is set! The Bard's automation begins.",
        "Henceforth, the backup shall run by the striking of the hour!",
        "Scheduled! Time itself now guards thy data.",
    ],
    "skip": [
        "Let it rest uncopied... for now.",
        "We shall revisit this tale another day.",
        "The project sleeps — perchance to dream of future backups.",
    ],
}

SAFETY_WARNINGS = [
    "Hold, villain! This directory bears the mark of the sensitive!",
    "By my troth, tread carefully — for here lie secrets most guarded!",
    "Stay thy hand! The contents herein are of a most delicate nature!",
]

PROGRESS_MESSAGES = [
    "The scribes are at work, copying with great haste...",
    "Patience, good soul — the transfer proceedeth...",
    "Quill meets parchment... the backup flows...",
    "The players rehearse their parts upon the drive...",
]

DRIVE_MESSAGES = [
    "Hark! What drives through yonder USB break?",
    "What external vessels await our precious cargo?",
    "Let us survey the harbors for worthy ships!",
]

FAREWELLS = [
    "Good night, good night! Parting is such sweet sorrow — but thy data is safe.",
    "The rest is silence... and well-backed-up repositories.",
    "All's well that ends well — and all is synced.",
    "Our revels now are ended. Go forth, for thy files are kept!",
    "If we shadows have offended, think but this and all is mended:\n  That you have but backed up, whilst these drives attended.",
]


def get_banner() -> str:
    return random.choice(BANNERS)


def get_confirmation(action: str) -> str:
    options = CONFIRMATIONS.get(action, CONFIRMATIONS["backup"])
    return random.choice(options)


def get_safety_warning() -> str:
    return random.choice(SAFETY_WARNINGS)


def get_progress_message() -> str:
    return random.choice(PROGRESS_MESSAGES)


def get_drive_message() -> str:
    return random.choice(DRIVE_MESSAGES)


def get_farewell() -> str:
    return random.choice(FAREWELLS)
