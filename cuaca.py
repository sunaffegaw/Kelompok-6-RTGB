# cuaca.py
"""
Frontend Streamlit untuk Weather Application.
Menggunakan backend OOP dari weather_backend.py
"""

import os
import streamlit as st
from weather_backend import (
    WeatherService,
    WeatherException,
    CityNotFoundException,
    APIRequestException,
    InvalidInputException
)

# ========== CONFIG ==========
API_KEY = os.getenv("WEATHER_API_KEY") or "549911d3a6e7599cdc30e240d375e356"

# ========== STREAMLIT SETUP ==========
st.set_page_config(page_title="Weather App", layout="centered")
st.title("🌤️ Weather App")
st.caption("Current weather + prediction. Pilih mode 'Hourly' atau 'Daily' lalu sesuaikan jumlah entri.")

# ========== INITIALIZE SERVICE ==========
@st.cache_resource
def get_weather_service():
    """
    Create and return WeatherService.
    This function avoids raising at import time by deferring client creation inside service (lazy).
    """
    return WeatherService(API_KEY)

try:
    weather_service = get_weather_service()
except Exception as e:
    # Should not normally happen because WeatherService is lazy,
    # but display user-friendly message if it does.
    st.error("Gagal inisialisasi WeatherService: " + str(e))
    st.stop()

# ========== UI: INPUT ==========
city = st.text_input("🔍 Search City..", placeholder="Masukkan nama kota...")

mode = st.radio("Mode prediksi:", options=["Hourly", "Daily"], index=0, horizontal=True)

if mode == "Hourly":
    n_entries = st.slider("Jumlah entri prediksi (hourly, tiap 3 jam):", min_value=1, max_value=40, value=8)
else:
    n_days = st.slider("Jumlah hari untuk ringkasan harian:", min_value=1, max_value=5, value=3)

# ========== SEARCH BUTTON ==========
if st.button("Search"):
    try:
        # BACKEND CALL: GET CURRENT WEATHER
        current_weather = weather_service.get_current_weather(city)

        # FRONTEND: DISPLAY CURRENT WEATHER
        st.markdown("---")
        st.subheader(f"📍 Cuaca di **{current_weather.city.title()}**")
        st.caption(f"Koordinat: {current_weather.latitude:.4f}°, {current_weather.longitude:.4f}°")

        c1, c2, c3, c4, c5, c6 = st.columns([1.6, 1, 1, 1, 1, 1])
        with c1:
            st.markdown("**Weather**")
            st.write(current_weather.description)
        with c2:
            st.markdown("**Icon**")
            st.image(f"https://openweathermap.org/img/wn/{current_weather.icon}@2x.png", width=64)
        with c3:
            st.markdown("**Temp (°C)**")
            st.metric(label="", value=f"{current_weather.temperature:.1f}")
        with c4:
            st.markdown("**Pressure (hPa)**")
            st.metric(label="", value=f"{current_weather.pressure}")
        with c5:
            st.markdown("**Humidity (%)**")
            st.metric(label="", value=f"{current_weather.humidity}")
        with c6:
            st.markdown("**Wind (m/s)**")
            st.metric(label="", value=f"{current_weather.wind_speed}")

        # BACKEND CALL: GET FORECAST
        st.markdown("---")
        st.subheader("🔮 Weather Prediction")

        if mode == "Hourly":
            df_hour = weather_service.get_hourly_forecast(
                current_weather.latitude,
                current_weather.longitude,
                n_entries
            )

            st.markdown(f"### Hourly forecast — next {len(df_hour)} entries (interval 3 jam)")
            df_hour_plot = df_hour.set_index("datetime")[["temp"]]
            st.line_chart(df_hour_plot)

            for _, row in df_hour.iterrows():
                col_t, col_i, col_d, col_temp, col_h, col_w = st.columns([1.2, 0.8, 2, 1, 1, 1])
                with col_t:
                    st.markdown(f"**{row['datetime'].strftime('%Y-%m-%d %H:%M')}**")
                with col_i:
                    st.image(f"https://openweathermap.org/img/wn/{row['icon']}@2x.png", width=48)
                with col_d:
                    st.write(row["desc"])
                with col_temp:
                    st.markdown("Temp")
                    st.write(f"{row['temp']:.1f} °C")
                with col_h:
                    st.markdown("Hum")
                    st.write(f"{row['humidity']} %")
                with col_w:
                    st.markdown("Wind")
                    st.write(f"{row['wind']} m/s")

        else:
            daily_df = weather_service.get_daily_forecast(
                current_weather.latitude,
                current_weather.longitude,
                n_days
            )

            st.markdown(f"### Daily summary — next {len(daily_df)} day(s)")
            df_plot = daily_df.set_index("date_str")[["mean_temp", "min_temp", "max_temp"]]
            st.line_chart(df_plot)

            for _, row in daily_df.iterrows():
                col_date, col_icon, col_desc, col_min, col_max, col_mean = st.columns([1.2, 0.6, 2, 1, 1, 1])
                with col_date:
                    st.markdown(f"**{row['date_str']}**")
                with col_icon:
                    st.image(f"https://openweathermap.org/img/wn/{row['icon']}@2x.png", width=48)
                with col_desc:
                    st.write(row["desc"])
                with col_min:
                    st.markdown("Min")
                    st.write(f"{row['min_temp']:.1f} °C")
                with col_max:
                    st.markdown("Max")
                    st.write(f"{row['max_temp']:.1f} °C")
                with col_mean:
                    st.markdown("Mean")
                    st.write(f"{row['mean_temp']:.1f} °C")

        st.caption("Sumber data: OpenWeatherMap (forecast 5 hari / 3 jam).")

    # ERROR HANDLING: tampilkan pesan spesifik sesuai exception
    except InvalidInputException as e:
        st.warning(f"⚠️ Input tidak valid: {str(e)}")

    except CityNotFoundException as e:
        st.error(f"❌ {str(e)}")
        st.info("💡 Tips: Cek ejaan atau coba nama kota dalam bahasa Inggris")

    except APIRequestException as e:
        st.error(f"🌐 API Error: {str(e)}")
        st.info("Silakan coba lagi dalam beberapa saat")

    except WeatherException as e:
        st.error(f"⚠️ Weather processing error: {str(e)}")

    except Exception as e:
        st.error(f"❌ Unexpected error: {str(e)}")
        st.info("Silakan hubungi administrator jika masalah berlanjut")



if not st.session_state.get("search_clicked", False):
    st.info("🔍 Masukkan nama kota lalu klik **Search** untuk melihat cuaca!")
