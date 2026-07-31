import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("calendar_adapter_weather_server", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class WeatherLocationTests(unittest.TestCase):
    def test_default_locations_match_portal_choices(self):
        self.assertEqual(
            SERVER.WEATHER_DEFAULT_CITY_KEYS,
            ("pohang", "daegu", "yeongcheon", "yeonghae"),
        )
        self.assertEqual(
            [SERVER.WEATHER_LOCATIONS[key]["label"] for key in SERVER.WEATHER_DEFAULT_CITY_KEYS],
            ["포항", "대구", "영천", "영해"],
        )

    def test_legacy_yeongdeok_history_remains_supported(self):
        self.assertEqual(SERVER.validate_weather_city("yeongdeok"), "yeongdeok")


if __name__ == "__main__":
    unittest.main()
