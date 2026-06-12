from pprint import pprint
import time


SYSTEM_PROMPT = """
Agent chỉ được kết luận khi đã có dữ liệu thời tiết hợp lệ.
Nếu dữ liệu thời tiết không có đủ temp_high hoặc rain_probability,
thì agent không được đưa ra gợi ý trang phục.
"""


# =========================
# TOOLS
# =========================

def get_weather(city: str, date: str) -> dict:
    time.sleep(5)
    raise TimeoutError("Weather API timeout")
    weather_data = {
        "Hà Nội": {
            "temp_low": 21,
            "temp_high": 25,
            "rain_probability": 0.7
        },
        "TP.HCM": {
            "temp_low": 28,
            "temp_high": 35,
            "rain_probability": 0.4
        },
        "Đà Nẵng": {
            "temp_low": 26,
            "temp_high": 31,
            "rain_probability": 0.6
        },
        "Hải Phòng": {
            "temp_low": 23,
            "temp_high": 27,
            "rain_probability": 0.8
        },
        "Cần Thơ": {
            "temp_low": 27,
            "temp_high": 34,
            "rain_probability": 0.5
        }
    }

    if city not in weather_data:
        raise ValueError(f"Không tìm thấy dữ liệu thời tiết cho thành phố: {city}")

    return {
        "city": city,
        "date": date,
        **weather_data[city]
    }


def recommend_outfit(temp_high: int, rain_probability: float) -> str:
    suggestions = []

    if temp_high >= 33:
        suggestions.append("Áo thun ngắn tay và quần short")
    elif temp_high >= 28:
        suggestions.append("Áo nhẹ, thoáng mát và quần dài mỏng")
    elif temp_high >= 24:
        suggestions.append("Áo sơ mi hoặc áo polo cùng quần jeans/khaki")
    else:
        suggestions.append("Áo khoác mỏng hoặc áo len nhẹ")

    if rain_probability >= 0.7:
        suggestions.append("Mang theo ô hoặc áo mưa")
    elif rain_probability >= 0.4:
        suggestions.append("Chuẩn bị áo khoác nhẹ đề phòng mưa")
    else:
        suggestions.append("Không cần ô, chỉ cần trang phục thoải mái")

    return ". ".join(suggestions)


# =========================
# SIMPLE REACT AGENT WITH TRACE
# =========================

def run_agent(city: str, date: str):
    print("SYSTEM PROMPT:")
    print(SYSTEM_PROMPT.strip())
    print("\n--- AGENT TRACE ---")

    thought = "Tôi cần dữ liệu thời tiết để có thể đưa ra gợi ý trang phục."
    print("Thought:", thought)

    try:
        action = f"get_weather(city={city!r}, date={date!r})"
        print("Action:", action)
        weather_info = get_weather(city, date)

        observation = "Đã thu thập dữ liệu thời tiết thành công."
        print("Observation:", observation)
        pprint(weather_info)

        if "temp_high" not in weather_info or "rain_probability" not in weather_info:
            raise ValueError("Dữ liệu thời tiết thiếu temp_high hoặc rain_probability.")

        thought = "Tôi đã có đủ dữ liệu, bắt đầu chọn trang phục phù hợp."
        print("Thought:", thought)

        action = (
            f"recommend_outfit(temp_high={weather_info['temp_high']}, "
            f"rain_probability={weather_info['rain_probability']})"
        )
        print("Action:", action)

        outfit_suggestion = recommend_outfit(
            temp_high=weather_info["temp_high"],
            rain_probability=weather_info["rain_probability"]
        )

        observation = "Đã suy luận gợi ý trang phục dựa trên dữ liệu thời tiết."
        print("Observation:", observation)

        print("\n--- FINAL ANSWER ---")
        print(f"Nhiệt độ tại {city} vào ngày {date}: {weather_info['temp_high']}°C")
        print(f"Trang phục phù hợp: {outfit_suggestion}")

    except Exception as error:
        print("Observation: Không thể hoàn thành tác vụ do thiếu dữ liệu thời tiết hợp lệ.")
        print(f"Error: {error}")
        print("Agent chỉ kết luận khi đã có weather data hợp lệ.")


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    city = input("Nhập tên thành phố: ").strip()
    if not city:
        print("Vui lòng nhập tên thành phố hợp lệ.")
    else:
        run_agent(
            city=city,
            date="2026-06-01"
        )
