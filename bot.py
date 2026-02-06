import os
import io
import asyncio
import requests
import matplotlib.pyplot as plt
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")


bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
users = {}


class UserProfileStates(StatesGroup):
    weight = State()
    height = State()
    age = State()
    activity = State()
    city = State()


class FoodStates(StatesGroup):
    waiting_for_grams = State()


def calculate_water(weight, activity_minutes, temperature):
    water = weight * 30
    water += (activity_minutes // 30) * 500
    if temperature > 25:
        water += 500
    return water


def calculate_calories(weight, height, age, activity_minutes):
    calories = 10 * weight + 6.25 * height - 5 * age
    calories += (activity_minutes // 30) * 200
    return calories


def get_current_temperature(city):
    url = "https://api.openweathermap.org/data/2.5/weather"
    response = requests.get(url, params={"q": city, "appid": OPENWEATHERMAP_API_KEY, "units": "metric"})
    if response.status_code == 200:
        data = response.json()
        current_temperature = data["main"]["temp"]
        return current_temperature
    print(f"Ошибка: {response.status_code}")
    return None


def get_food_info(product_name):
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        products = data.get("products", [])
        if products:  # Проверяем, есть ли найденные продукты
            first_product = products[0]
            return {
                "name": first_product.get("product_name", "Неизвестно"),
                "calories": first_product.get("nutriments", {}).get("energy-kcal_100g", 0)
            }
        return None
    print(f"Ошибка: {response.status_code}")
    return None


def cumulative_plot(values, title, ylabel):
    cumulative = []
    total = 0
    for v in values:
        total += v
        cumulative.append(total)

    plt.figure()
    plt.plot(cumulative, marker="o")
    plt.title(title)
    plt.xlabel("Событие")
    plt.ylabel(ylabel)
    plt.grid(True)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Привет!\nЯ помогу тебе похудеть, считая воду, калории и тренировки.\nНачни с команды /set_profile")


@dp.message(Command("set_profile"))
async def set_profile(message: Message, state: FSMContext):
    await message.answer("Введите ваш вес (кг):")
    await state.set_state(UserProfileStates.weight)


@dp.message(StateFilter(UserProfileStates.weight))
async def get_weight(message: Message, state: FSMContext):
    await state.update_data(weight=int(message.text))
    await message.answer("Введите ваш рост (см):")
    await state.set_state(UserProfileStates.height)


@dp.message(StateFilter(UserProfileStates.height))
async def get_height(message: Message, state: FSMContext):
    await state.update_data(height=int(message.text))
    await message.answer("Введите ваш возраст:")
    await state.set_state(UserProfileStates.age)


@dp.message(StateFilter(UserProfileStates.age))
async def get_age(message: Message, state: FSMContext):
    await state.update_data(age=int(message.text))
    await message.answer("Сколько минут активности у вас в день?")
    await state.set_state(UserProfileStates.activity)


@dp.message(StateFilter(UserProfileStates.activity))
async def get_activity(message: Message, state: FSMContext):
    await state.update_data(activity=int(message.text))
    await message.answer("В каком городе вы находитесь?")
    await state.set_state(UserProfileStates.city)


@dp.message(StateFilter(UserProfileStates.city))
async def get_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    data = await state.get_data()
    current_temperature = get_current_temperature(data["city"])
    users[message.from_user.id] = {"weight": data["weight"],
                                   "height": data["height"],
                                   "age": data["age"],
                                   "activity": data["activity"],
                                   "city": data["city"],
                                   "water_goal": calculate_water(data["weight"], data["activity"], current_temperature),
                                   "calorie_goal": calculate_calories(data["weight"], data["height"], data["age"], data["activity"]),
                                   "logged_water": 0,
                                   "logged_calories": 0,
                                   "burned_calories": 0,
                                   "water_log": [],        
                                   "calorie_log": []}

    await message.answer(f"Профиль создан!\nНорма воды: {users[message.from_user.id]['water_goal']} мл\nНорма калорий: {users[message.from_user.id]['calorie_goal']} ккал")
    await state.clear()


@dp.message(Command("log_water"))
async def log_water(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала создай профиль через /set_profile")
        return
    try:
        water_drunk_amount = int(message.text.split()[1])
        users[user_id]["logged_water"] += water_drunk_amount
        users[user_id]["water_log"].append(water_drunk_amount)
        left_water_to_drink = users[user_id]["water_goal"] - users[user_id]["logged_water"]
        await message.answer(f"Ты выпил {water_drunk_amount} мл воды. Осталось: {left_water_to_drink} мл")
    except:
        await message.answer("Ошибка: Используй /log_water <количество>")


@dp.message(Command("log_food"))
async def log_food_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала создай профиль через /set_profile")
        return
    try:
        product_name = message.text.split(maxsplit=1)[1]
        product_info = get_food_info(product_name)
        if product_info is None:
            await message.answer("Продукт не найден")
            return

        await state.update_data(food_name=product_info['name'], kcal_per_100g=product_info['calories'])
        await message.answer(f"{product_info['name']} — {product_info['calories']} ккал на 100 г.\nСколько грамм вы съели?")
        await state.set_state(FoodStates.waiting_for_grams)
    except IndexError:
        await message.answer("Ошибка: Используй /log_food <название продукта>")

@dp.message(StateFilter(FoodStates.waiting_for_grams))
async def log_food_grams(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала создай профиль через /set_profile")
        return
    data = await state.get_data()
    try:
        user = users[user_id]
        grams = float(message.text)
        kcal = grams * data['kcal_per_100g'] / 100
        # Чем больше воды, тем меньше калорий. Это мое продвинутое определение калорийности (хотя скорее всего с реальностью оно не мэтчится)
        factor = max(0.5, 1 - user['logged_water'] / user['water_goal'])
        kcal = round(kcal * factor, 1)
        user['logged_calories'] += kcal
        user['calorie_log'].append(kcal)

        await message.answer(f"Записано: {round(kcal, 1)} ккал")
    except ValueError:
        await message.answer("Ошибка: Пожалуйста, введи число (граммы)")
    await state.clear()



DICT_WORKOUT_X_CALORIES_PER_MINUTE = {"бег": 10, "ходьба": 5, "велосипед": 8, "силовая тренировка": 5, "плавание": 7}
@dp.message(Command("log_workout"))
async def log_workout(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала создай профиль через /set_profile")
        return
    try:
        message_parts = message.text.split()
        workout_type = " ".join(message_parts[1:-1])
        minutes = int(message_parts[-1])
        burned_calories = DICT_WORKOUT_X_CALORIES_PER_MINUTE[workout_type] * minutes
        users[user_id]["burned_calories"] += burned_calories
        extra_water = (minutes // 30) * 200
        users[user_id]["logged_water"] += extra_water
        await message.answer(f"{workout_type} {minutes} мин — {burned_calories} ккал. Дополнительно: {extra_water} мл воды")
    except:
        await message.answer("Ошибка: Используй /log_workout <тип> <минуты>")


@dp.message(Command("check_progress"))
async def check_progress(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала создай профиль через /set_profile")
        return
    user = users[user_id]
    logged_water = round(user['logged_water'])
    water_goal = round(user['water_goal'])
    need_water = round(water_goal - logged_water) if water_goal - logged_water > 0 else 0
    logged_calories = round(user['logged_calories'])
    calorie_goal = round(user["calorie_goal"])
    burned_calories = round(user['burned_calories'])
    balance = round(logged_calories - burned_calories)

    water_answer = f"📊 Прогресс:\nВода:\n- Выпито: {logged_water} мл из {water_goal} мл.\n- Осталось: {need_water} мл.\n\n"
    calories_answer = f"Калории:\n- Потреблено: {logged_calories} ккал из {calorie_goal} ккал.\n- Сожжено: {burned_calories} ккал.\n- Баланс: {balance} ккал."
    answer = water_answer + calories_answer
    await message.answer(answer)


@dp.message(Command("show_graphs"))
async def show_graphs(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала создай профиль через /set_profile")
        return
    user = users[user_id]

    if user["water_log"]:
        water_img = cumulative_plot(user["water_log"], "Кумулятивный прогресс по воде", "мл")
        await message.answer_photo(BufferedInputFile(water_img.read(), filename="water.png"))

    if user["calorie_log"]:
        calories_img = cumulative_plot(user["calorie_log"], "Кумулятивные калории", "ккал")
        await message.answer_photo(BufferedInputFile(calories_img.read(), filename="calories.png"))


# Рекомендации делаем статичными
RECOMMENDED_FOODS = ["Куриная грудка", "Творог 0%", "Овощи", "Яблоки", "Овсянка"]
RECOMMENDED_SNACKS = ["Морковь", "Яблоко", "Йогурт", "Протеиновый батончик"]
RECOMMENDED_WORKOUTS = ["Кардио 30 минут", "Интервальные 20 минут", "Ходьба 40 минут", "Силовая 30 минут"]

@dp.message(Command("recommended_food"))
async def recommended_food(message):
    await message.answer("Рекомендованные продукты питания:\n- " + ", ".join(RECOMMENDED_FOODS))


@dp.message(Command("recommended_snack"))
async def recommended_snack(message):
    await message.answer("Рекомендованные продукты для перекуса:\n- " + ", ".join(RECOMMENDED_SNACKS))


@dp.message(Command("recommended_workout"))
async def recommended_workout(message):
    await message.answer("Рекомендованные тренировки:\n- " + ", ".join(RECOMMENDED_WORKOUTS))


async def main():
    print("Бот запущен")
    await dp.start_polling(bot)

if name == "__main__":
    asyncio.run(main())
