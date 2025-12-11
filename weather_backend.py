"""
weather_backend.py
Backend OOP untuk Weather App.

Public API (yang digunakan oleh frontend):
- WeatherService
- WeatherException, CityNotFoundException, APIRequestException, InvalidInputException
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict
import requests
import pandas as pd


# ========== EXCEPTIONS ==========
class WeatherException(Exception):
    """Base exception untuk weather-related errors"""
    pass


class CityNotFoundException(WeatherException):
    """Raised ketika kota tidak ditemukan"""
    pass


class APIRequestException(WeatherException):
    """Raised ketika API request gagal"""
    pass


class InvalidInputException(WeatherException):
    """Raised ketika input tidak valid"""
    pass


# ========== DATA MODELS ==========
@dataclass
class CurrentWeather:
    city: str
    description: str
    icon: str
    temperature: float
    pressure: int
    humidity: int
    wind_speed: float
    latitude: float
    longitude: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "city": self.city,
            "description": self.description,
            "icon": self.icon,
            "temperature": self.temperature,
            "pressure": self.pressure,
            "humidity": self.humidity,
            "wind_speed": self.wind_speed,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


# ========== API CLIENT ==========
class WeatherAPIClient:
    """
    Client untuk berkomunikasi dengan OpenWeatherMap.
    NOTE: client ini **menganggap** api_key valid; pengecekan ketersediaan key
    dilakukan oleh layer yang memanggilnya (WeatherService).
    """

    BASE_URL_CURRENT = "https://api.openweathermap.org/data/2.5/weather"
    BASE_URL_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"

    def __init__(self, api_key: str, timeout: int = 10):
        if not api_key or api_key.strip() == "":
            raise ValueError("API key tidak boleh kosong bagi WeatherAPIClient")
        self.api_key = api_key
        self.timeout = timeout

    def _do_get(self, url: str, params: dict) -> dict:
        params = params.copy()
        params["appid"] = self.api_key
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
        except requests.Timeout:
            raise APIRequestException("Request timeout saat menghubungi Weather API")
        except requests.RequestException as e:
            raise APIRequestException(f"Network error saat menghubungi Weather API: {str(e)}")

        if resp.status_code == 404:
            # OpenWeather memberi 404 jika resource tidak ditemukan (mis. city)
            # Response body biasanya berisi {"cod":"404","message":"city not found"}
            try:
                msg = resp.json().get("message", "Not found")
            except Exception:
                msg = resp.text
            raise CityNotFoundException(f"{msg} (status 404)")

        if resp.status_code != 200:
            try:
                msg = resp.json().get("message", resp.text)
            except Exception:
                msg = resp.text
            raise APIRequestException(f"API responded with status {resp.status_code}: {msg}")

        try:
            return resp.json()
        except Exception:
            raise APIRequestException("Gagal decode JSON dari response API")

    def fetch_current_weather(self, city_name: str) -> dict:
        params = {"q": city_name, "units": "metric", "lang": "en"}
        return self._do_get(self.BASE_URL_CURRENT, params)

    def fetch_forecast(self, latitude: float, longitude: float) -> dict:
        params = {"lat": latitude, "lon": longitude, "units": "metric", "lang": "en"}
        return self._do_get(self.BASE_URL_FORECAST, params)


# ========== DATA PROCESSOR ==========
class WeatherDataProcessor:
    """Transform raw JSON menjadi objek / DataFrame yang dipakai frontend."""

    @staticmethod
    def to_local_datetime(dt_utc: int, tz_offset: int = 0) -> datetime:
        return datetime.utcfromtimestamp(dt_utc) + timedelta(seconds=tz_offset)

    @staticmethod
    def parse_current_weather(raw: dict, city_name: str) -> CurrentWeather:
        try:
            return CurrentWeather(
                city=city_name,
                description=raw["weather"][0]["description"].capitalize(),
                icon=raw["weather"][0]["icon"],
                temperature=float(raw["main"]["temp"]),
                pressure=int(raw["main"]["pressure"]),
                humidity=int(raw["main"]["humidity"]),
                wind_speed=float(raw.get("wind", {}).get("speed", 0.0)),
                latitude=float(raw["coord"]["lat"]),
                longitude=float(raw["coord"]["lon"]),
            )
        except (KeyError, IndexError, TypeError) as e:
            raise WeatherException(f"Error parsing current weather: {str(e)}")

    @staticmethod
    def build_forecast_dataframe(forecast_json: dict) -> pd.DataFrame:
        try:
            tz_offset = forecast_json.get("city", {}).get("timezone", 0)
            rows = []
            for entry in forecast_json.get("list", []):
                dt_utc = entry["dt"]
                dt_local = WeatherDataProcessor.to_local_datetime(dt_utc, tz_offset)
                rows.append({
                    "dt": dt_utc,
                    "datetime": dt_local,
                    "date": dt_local.date(),
                    "temp": float(entry["main"]["temp"]),
                    "humidity": int(entry["main"]["humidity"]),
                    "wind": float(entry.get("wind", {}).get("speed", 0.0)),
                    "desc": entry["weather"][0]["description"].capitalize(),
                    "icon": entry["weather"][0]["icon"],
                })
            df = pd.DataFrame(rows)
            return df
        except (KeyError, IndexError, TypeError) as e:
            raise WeatherException(f"Error building forecast dataframe: {str(e)}")

    @staticmethod
    def aggregate_daily_forecast(df: pd.DataFrame, n_days: int = 5) -> pd.DataFrame:
        try:
            agg = df.groupby("date").agg(
                min_temp=("temp", "min"),
                max_temp=("temp", "max"),
                mean_temp=("temp", "mean"),
                mean_hum=("humidity", "mean"),
                mean_wind=("wind", "mean")
            ).reset_index()

            rep = df.groupby("date").agg({
                "icon": lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0],
                "desc": lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0]
            }).reset_index()

            daily = pd.merge(agg, rep, on="date")
            daily["date_str"] = daily["date"].astype(str)
            return daily.head(max(1, min(n_days, 5)))
        except Exception as e:
            raise WeatherException(f"Error aggregating daily forecast: {str(e)}")


# ========== SERVICE LAYER ==========
class WeatherService:
    """
    Facade/orchestrator dipakai oleh UI.

    Important: konstruktur TIDAK melempar exception walau API key kosong.
    Pembuatan WeatherAPIClient dilakukan LOKAL pada saat panggilan API (lazy),
    sehingga frontend dapat *import* module tanpa blank page.
    """

    def __init__(self, api_key: str = None):
        # simpan key; jangan langsung buat API client supaya frontend tidak error saat import
        self._api_key = api_key
        self._api_client = None
        self._processor = WeatherDataProcessor()

    def _ensure_client(self):
        if self._api_client is None:
            if not self._api_key:
                raise APIRequestException("API key tidak ditemukan. Set environment variable 'WEATHER_API_KEY' atau gunakan st.secrets.")
            self._api_client = WeatherAPIClient(self._api_key)

    def validate_city_input(self, city: str) -> str:
        if not city or city.strip() == "":
            raise InvalidInputException("Nama kota tidak boleh kosong")
        normalized = city.strip()
        if len(normalized) < 2:
            raise InvalidInputException("Nama kota terlalu pendek (min 2 karakter)")
        return normalized

    def get_current_weather(self, city: str) -> CurrentWeather:
        normalized = self.validate_city_input(city)
        # prepare client
        self._ensure_client()
        raw = self._api_client.fetch_current_weather(normalized)
        # parse
        return self._processor.parse_current_weather(raw, normalized)

    def get_hourly_forecast(self, latitude: float, longitude: float, n_entries: int = 8) -> pd.DataFrame:
        n_entries = max(1, min(int(n_entries), 40))
        self._ensure_client()
        raw = self._api_client.fetch_forecast(latitude, longitude)
        df = self._processor.build_forecast_dataframe(raw)
        return df.head(n_entries).copy()

    def get_daily_forecast(self, latitude: float, longitude: float, n_days: int = 3) -> pd.DataFrame:
        n_days = max(1, min(int(n_days), 5))
        self._ensure_client()
        raw = self._api_client.fetch_forecast(latitude, longitude)
        df = self._processor.build_forecast_dataframe(raw)
        daily = self._processor.aggregate_daily_forecast(df, n_days)
        return daily

# End of file
