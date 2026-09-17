"""Звіряє, що admin_panel's derive_device_secret (app/device_auth.py) досі побітово збігається
з формулою в кореневому utils.py (websocket_server/update_server звіряють HMAC саме за нею) -
дві копії однієї формули, синхронізовані лише коментарем, ніщо на рівні імпорту/типів не
ловить розбіжність. Обидва модулі читають DEVICE_AUTH_MASTER_SECRET з того самого env var при
імпорті (типово однаковий дефолт "change-me-in-production" у тестовому середовищі), тож цей
тест реально перевіряє саме формулу (регістр chip_id, роздільник, порядок полів), а не сам
секрет."""

import utils
from app.device_auth import derive_device_secret as admin_panel_derive


def test_admin_panel_matches_root_utils_for_various_inputs():
    cases = [
        ("a1b2c3d4e5f6", 0),
        ("A1B2C3D4E5F6", 0),  # регістр вже змішаний - обидві формули мають upper() однаково
        ("000000000000", 1),
        ("ffffffffffff", 42),
    ]
    for chip_id, secret_version in cases:
        assert admin_panel_derive(chip_id, secret_version) == utils.derive_device_secret(
            chip_id, secret_version
        ), f"розбіжність формули для chip_id={chip_id!r} version={secret_version}"


def test_admin_panel_matches_root_utils_secret_version_sensitivity():
    # Обидві формули мають включати secret_version у підпис - інакше ротація секрету
    # (bump secret_version) мовчки нічого не змінювала б у похідному значенні.
    a = admin_panel_derive("deadbeefcafe", 1)
    b = admin_panel_derive("deadbeefcafe", 2)
    assert a != b
    assert utils.derive_device_secret("deadbeefcafe", 1) != utils.derive_device_secret("deadbeefcafe", 2)
