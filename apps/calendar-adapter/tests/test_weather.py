import importlib.util
import pathlib
import unittest
from unittest import mock


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

    def test_current_location_rejects_past_dates(self):
        yesterday = SERVER.datetime.now(SERVER.LOCAL_TIMEZONE).date() - SERVER.timedelta(days=1)
        with self.assertRaisesRegex(ValueError, "current_location_weather_future_only"):
            SERVER.current_location_weather_payload(
                {"latitude": 36.019, "longitude": 129.3435, "date": yesterday.isoformat()}
            )

    def test_current_location_validates_coordinates(self):
        with self.assertRaisesRegex(ValueError, "invalid_latitude"):
            SERVER.current_location_weather_payload(
                {"latitude": 91, "longitude": 129.3435, "date": SERVER.datetime.now(SERVER.LOCAL_TIMEZONE).date().isoformat()}
            )

    @mock.patch.object(SERVER, "reverse_geocode_location", return_value="Pohang")
    @mock.patch.object(SERVER, "fetch_open_meteo_forecast_coordinates")
    def test_current_location_returns_forecast_without_coordinates(self, fetch_forecast, reverse_geocode):
        target_date = SERVER.datetime.now(SERVER.LOCAL_TIMEZONE).date().isoformat()
        fetch_forecast.return_value = {
            "daily": {
                "time": [target_date],
                "weather_code": [0],
                "temperature_2m_min": [21.2],
                "temperature_2m_max": [31.8],
            },
            "hourly": {
                "time": [f"{target_date}T09:00"],
                "weather_code": [0],
                "temperature_2m": [26.4],
            },
        }

        payload = SERVER.current_location_weather_payload(
            {"latitude": 36.019, "longitude": 129.3435, "date": target_date, "language": "en"}
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["item"]["city"], "current")
        self.assertEqual(payload["item"]["cityName"], "Pohang")
        self.assertEqual(payload["item"]["locationAttribution"], "© OpenStreetMap contributors")
        self.assertNotIn("latitude", payload)
        self.assertNotIn("longitude", payload)
        reverse_geocode.assert_called_once_with(36.019, 129.3435, "en")

    @mock.patch.object(SERVER, "weather_history_map", return_value={})
    @mock.patch.object(SERVER, "fetch_open_meteo_forecast")
    def test_month_weather_caps_forecast_to_provider_horizon(self, fetch_forecast, weather_history_map):
        today = SERVER.datetime.now(SERVER.LOCAL_TIMEZONE).date()
        capped_end = today + SERVER.timedelta(days=SERVER.OPEN_METEO_FORECAST_MAX_DAYS - 1)
        visible_end = today + SERVER.timedelta(days=41)
        fetch_forecast.return_value = {
            "daily": {
                "time": [today.isoformat(), capped_end.isoformat()],
                "weather_code": [0, 3],
                "temperature_2m_min": [21, 24],
                "temperature_2m_max": [31, 34],
            },
            "hourly": {
                "time": [f"{today.isoformat()}T09:00"],
                "weather_code": [0],
                "temperature_2m": [26],
            },
        }

        payload = SERVER.month_weather_payload(
            {
                "city": ["pohang"],
                "start": [today.isoformat()],
                "end": [visible_end.isoformat()],
            }
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["error"], "")
        self.assertEqual(payload["end"], visible_end.isoformat())
        self.assertEqual([item["date"] for item in payload["items"]], [today.isoformat(), capped_end.isoformat()])
        fetch_forecast.assert_called_once_with("pohang", today.isoformat(), capped_end.isoformat())


if __name__ == "__main__":
    unittest.main()
