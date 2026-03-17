from __future__ import annotations

from pathlib import Path

from clawlite.core.memory_privacy import (
    decrypt_text_for_category,
    encrypt_text_for_category,
    load_or_create_privacy_key,
    privacy_block_reason,
    xor_with_keystream,
)


def test_load_or_create_privacy_key_creates_reusable_32_byte_key(tmp_path: Path) -> None:
    path = tmp_path / "privacy.key"
    diagnostics: dict[str, object] = {}

    key = load_or_create_privacy_key(
        cached_key=None,
        privacy_key_path=path,
        diagnostics=diagnostics,
    )
    loaded = load_or_create_privacy_key(
        cached_key=None,
        privacy_key_path=path,
        diagnostics=diagnostics,
    )

    assert isinstance(key, bytes)
    assert len(key) == 32
    assert loaded == key


def test_encrypt_and_decrypt_text_for_category_roundtrip() -> None:
    diagnostics: dict[str, object] = {}
    key = b"k" * 32
    settings = {"encrypted_categories": ["context"]}

    encrypted = encrypt_text_for_category(
        "secret context text",
        "context",
        settings=settings,
        privacy_settings_loader=lambda: settings,
        load_or_create_privacy_key_fn=lambda: key,
        xor_with_keystream_fn=xor_with_keystream,
        diagnostics=diagnostics,
    )
    decrypted = decrypt_text_for_category(
        encrypted,
        "context",
        settings=settings,
        load_or_create_privacy_key_fn=lambda: key,
        xor_with_keystream_fn=xor_with_keystream,
        diagnostics=diagnostics,
    )

    assert encrypted.startswith("enc:v2:")
    assert decrypted == "secret context text"


def test_privacy_block_reason_matches_configured_pattern() -> None:
    reason = privacy_block_reason(
        "meu token secreto e abc123",
        privacy_settings_loader=lambda: {"never_memorize_patterns": ["token secreto"]},
    )

    assert reason == "pattern:token secreto"
