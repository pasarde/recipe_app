import os
import requests
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import random
import logging
from datetime import datetime
import bleach

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Load environment variables
load_dotenv()
SPOONACULAR_KEY = os.getenv("SPOONACULAR_KEY")
THEMEALDB_BASE_URL = "https://www.themealdb.com/api/json/v1/1"
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", os.urandom(24).hex())
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}
app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = 300

# Setup CSRF protection
csrf = CSRFProtect(app)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
cache = Cache(app)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class UserRecipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    ingredients = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    cuisine = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    region = db.Column(db.String(100), nullable=True)
    image = db.Column(db.String(200), nullable=True)
    likes = db.Column(db.Integer, default=0)
    saves = db.Column(db.Integer, default=0)

class Interaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipe_source = db.Column(db.String(50), nullable=False)
    recipe_id = db.Column(db.String(100), nullable=False)
    interaction_type = db.Column(db.String(20), nullable=False)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipe_source = db.Column(db.String(50), nullable=True)
    recipe_id = db.Column(db.String(100), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user = db.relationship("User", backref="comments", lazy=True)

class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(200), nullable=False)
    cuisine = db.Column(db.String(50), nullable=True)
    region = db.Column(db.String(100), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    count = db.Column(db.Integer, default=1)

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]

# API Functions
@cache.memoize(timeout=300)
def suggest_western_recipes_by_name(query, number=5, max_time=None, diet=None):
    """Fetch Western recipes by name from Spoonacular API."""
    url = "https://api.spoonacular.com/recipes/complexSearch"
    params = {
        "apiKey": SPOONACULAR_KEY,
        "query": query,
        "number": number,
        "addRecipeInformation": True,
        "instructionsRequired": True,
        "type": "main course"
    }
    if max_time:
        params["maxReadyTime"] = max_time
    if diet:
        params["diet"] = diet
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            logging.error(f"Spoonacular API error: {response.status_code} - {response.text}")
            return []
        results = response.json().get("results", [])
        return [{"id": str(r["id"]), "title": r["title"], "source": "spoonacular", "image": r.get("image", "/static/assets/default_recipe.jpg")} for r in results]
    except requests.RequestException:
        logging.error("Spoonacular API request failed")
        return []

@cache.memoize(timeout=300)
def suggest_western_recipes_by_ingredients(ingredients, number=5, max_time=None, diet=None):
    """Fetch Western recipes by ingredients from Spoonacular API."""
    url = "https://api.spoonacular.com/recipes/findByIngredients"
    params = {
        "apiKey": SPOONACULAR_KEY,
        "ingredients": ",".join(ingredients),
        "number": number,
        "ranking": 1
    }
    if max_time:
        params["maxReadyTime"] = max_time
    if diet:
        params["diet"] = diet
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            logging.error(f"Spoonacular API error: {response.status_code} - {response.text}")
            return []
        return [{"id": str(r["id"]), "title": r["title"], "source": "spoonacular", "image": r.get("image", "/static/assets/default_recipe.jpg")} for r in response.json()]
    except requests.RequestException:
        logging.error("Spoonacular API request failed")
        return []

@cache.memoize(timeout=300)
def suggest_indonesian_recipes_by_name(query, region=None, number=5):
    """Fetch Indonesian recipes by name from TheMealDB API or fallback data."""
    base_query = query.strip().lower()
    url = f"{THEMEALDB_BASE_URL}/search.php?s={base_query}"
    logging.debug(f"Requesting TheMealDB API: {url}")
    
    # Fallback data for common Indonesian recipes with reliable image URLs
    fallback_recipes = [
        {
            "id": "rendang",
            "title": "Beef Rendang",
            "source": "fallback",
            "image": "https://www.themealdb.com/images/media/meals/ypxrvg1515362401.jpg",  # URL yang valid
            "region": "Sumatra",
            "ingredients": ["500g beef", "400ml coconut milk", "2 lemongrass stalks", "5 kaffir lime leaves", "2 turmeric leaves", "10 shallots", "5 garlic cloves", "5 red chilies", "1 inch ginger", "1 inch galangal", "1 tsp turmeric powder", "Salt to taste"],
            "instructions": "Blend shallots, garlic, chilies, ginger, galangal, and turmeric into a paste. Cook the paste with lemongrass, lime leaves, and turmeric leaves until fragrant. Add beef and coconut milk, simmer for 3-4 hours until the sauce thickens and the beef is tender. Season with salt."
        },
        {
            "id": "soto",
            "title": "Soto Ayam",
            "source": "fallback",
            "image": "https://www.themealdb.com/images/media/meals/8mpqzz1508507655.jpg",
            "region": "Java",
            "ingredients": ["500g chicken", "2L water", "2 lemongrass stalks", "3 kaffir lime leaves", "2 bay leaves", "5 shallots", "3 garlic cloves", "1 inch ginger", "1 tsp turmeric powder", "1 tsp coriander powder", "Salt to taste", "Vermicelli noodles", "Boiled eggs", "Lime wedges"],
            "instructions": "Boil chicken in water with lemongrass, lime leaves, and bay leaves. Blend shallots, garlic, ginger, turmeric, and coriander into a paste. Sauté the paste until fragrant, then add to the broth. Simmer for 30 minutes. Shred the chicken. Serve with vermicelli, boiled eggs, and lime wedges."
        },
        {
            "id": "gudeg",
            "title": "Gudeg Jogja",
            "source": "fallback",
            "image": "https://www.themealdb.com/images/media/meals/1529445893.jpg",
            "region": "Java",
            "ingredients": ["1kg young jackfruit", "500ml coconut milk", "200g palm sugar", "5 shallots", "3 garlic cloves", "5 candlenuts", "1 tsp coriander powder", "2 bay leaves", "2 teak leaves", "Salt to taste"],
            "instructions": "Boil jackfruit until tender. Blend shallots, garlic, candlenuts, and coriander into a paste. Cook the paste with coconut milk, palm sugar, bay leaves, teak leaves, and jackfruit. Simmer for 4-5 hours until the jackfruit is soft and the sauce thickens. Season with salt."
        },
        {
            "id": "satay",
            "title": "Chicken Satay",
            "source": "fallback",
            "image": "https://www.themealdb.com/images/media/meals/1526418975.jpg",
            "region": "Java",
            "ingredients": ["500g chicken", "2 tbsp soy sauce", "2 tbsp peanut butter", "1 tbsp lime juice", "5 shallots", "3 garlic cloves", "1 tsp turmeric powder", "1 tsp coriander powder", "Skewers"],
            "instructions": "Blend shallots, garlic, turmeric, and coriander into a paste. Marinate chicken with the paste, soy sauce, peanut butter, and lime juice for 1 hour. Skewer the chicken and grill until cooked. Serve with peanut sauce."
        },
        {
            "id": "nasi_goreng",
            "title": "Nasi Goreng",
            "source": "fallback",
            "image": "https://www.themealdb.com/images/media/meals/1529445893.jpg",
            "region": "Java",
            "ingredients": ["2 cups cooked rice", "100g chicken", "2 eggs", "5 shallots", "3 garlic cloves", "2 red chilies", "1 tbsp soy sauce", "1 tbsp sweet soy sauce", "Salt to taste", "Fried shallots"],
            "instructions": "Blend shallots, garlic, and chilies into a paste. Sauté the paste until fragrant. Add chicken and cook until done. Push to the side, scramble the eggs. Add rice, soy sauce, sweet soy sauce, and salt. Stir-fry until mixed. Garnish with fried shallots."
        },
        {
            "id": "soto_banjar",
            "title": "Soto Banjar",
            "source": "fallback",
            "image": "https://www.themealdb.com/images/media/meals/8mpqzz1508507655.jpg",
            "region": "Kalimantan Selatan",
            "ingredients": ["500g chicken", "2L water", "2 lemongrass stalks", "3 kaffir lime leaves", "2 cloves", "2 star anise", "5 shallots", "3 garlic cloves", "1 inch ginger", "1 tsp turmeric powder", "Salt to taste", "Rice cakes", "Boiled eggs"],
            "instructions": "Boil chicken with lemongrass, lime leaves, cloves, and star anise. Blend shallots, garlic, ginger, and turmeric into a paste. Sauté the paste until fragrant, then add to the broth. Simmer for 30 minutes. Shred the chicken. Serve with rice cakes and boiled eggs."
        }
    ]
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            logging.error(f"TheMealDB API error: {response.status_code} - {response.text}")
            results = []
        else:
            try:
                data = response.json()
                # Pastikan data adalah dict dan punya key 'meals', kalau tidak set ke list kosong
                if not isinstance(data, dict):
                    logging.error(f"TheMealDB API returned invalid JSON format: {data}")
                    results = []
                else:
                    results = data.get("meals", []) or []
            except ValueError as e:
                logging.error(f"Failed to parse TheMealDB API response as JSON: {e}")
                results = []
        
        # Pastikan results adalah list sebelum iterasi
        if results is None:
            logging.warning(f"TheMealDB API returned None for meals, falling back to empty list")
            results = []
        
        for meal in results:
            if not meal.get("strMealThumb"):
                logging.warning(f"No image found for meal: {meal.get('strMeal')}")
        
        if not results:
            logging.warning(f"No results found for query: {base_query}, falling back to static data")
            results = [recipe for recipe in fallback_recipes if base_query in recipe["title"].lower()]
        
        # Filter by region if specified
        if region and region != "All Regions":
            filtered_results = [
                r for r in results 
                if (region.lower() in r.get("strArea", "").lower() if isinstance(r, dict) else False) or 
                   (region.lower() in r.get("strCategory", "").lower() if isinstance(r, dict) else False) or 
                   (region.lower() in r.get("strMeal", "").lower() if isinstance(r, dict) else False) or 
                   (r.get("region", "").lower() == region.lower() if isinstance(r, dict) else False)
            ]
            # If no API results match region, use fallback
            if not filtered_results:
                filtered_results = [
                    r for r in fallback_recipes 
                    if base_query in r["title"].lower() and r.get("region", "").lower() == region.lower()
                ]
            results = filtered_results[:number]
        else:
            results = results[:number]
        
        # Format results from TheMealDB or fallback with fallback image
        formatted_results = [
            {
                "id": str(r["idMeal"] if isinstance(r, dict) and "idMeal" in r else r["id"]),
                "title": r["strMeal"] if isinstance(r, dict) and "strMeal" in r else r["title"],
                "source": "themealdb" if isinstance(r, dict) and "idMeal" in r else "fallback",
                "image": r["strMealThumb"] if isinstance(r, dict) and "strMealThumb" in r and r["strMealThumb"] else (r["image"] if isinstance(r, dict) and r.get("image") else "/static/assets/default_recipe.jpg")
            }
            for r in results
        ]
        
        if not formatted_results:
            logging.warning(f"No results after filtering for query: {base_query}, region: {region}")
            # Use fallback if no results after filtering
            formatted_results = [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "source": "fallback",
                    "image": r["image"] if r["image"] else "/static/assets/default_recipe.jpg"
                }
                for r in fallback_recipes if base_query in r["title"].lower()
            ][:number]
        
        return formatted_results
    except requests.RequestException as e:
        logging.error(f"TheMealDB API request failed: {e}")
        # Fallback to static data on error
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "source": "fallback",
                "image": r["image"] if r["image"] else "/static/assets/default_recipe.jpg"
            }
            for r in fallback_recipes if base_query in r["title"].lower()
        ][:number]

@cache.memoize(timeout=300)
def get_weather_by_coords(lat, lon):
    """Fetch weather data for given coordinates from OpenWeatherMap API."""
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            logging.error(f"OpenWeatherMap API error: {response.status_code} - {response.text}")
            return None
        data = response.json()
        return {
            "city": data["name"],
            "condition": data["weather"][0]["description"],
            "temp": data["main"]["temp"],
            "weather_main": data["weather"][0]["main"]
        }
    except requests.RequestException:
        logging.error("OpenWeatherMap API request failed")
        return None

@cache.memoize(timeout=300)
def get_weather(city):
    """Fetch weather data for a city from OpenWeatherMap API."""
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            logging.error(f"OpenWeatherMap API error: {response.status_code} - {response.text}")
            return None
        data = response.json()
        return {
            "city": city,
            "condition": data["weather"][0]["description"],
            "temp": data["main"]["temp"],
            "weather_main": data["weather"][0]["main"]
        }
    except requests.RequestException:
        logging.error("OpenWeatherMap API request failed")
        return None

def get_random_recipes(number=5):
    """Get random recipes from multiple sources."""
    western = suggest_western_recipes_by_name("main course", number=number)
    indo = suggest_indonesian_recipes_by_name("indonesian", number=number)
    user_recipes = UserRecipe.query.limit(number).all()
    user_formatted = [{"id": str(r.id), "title": r.title, "source": "user", "image": r.image or "/static/assets/default_recipe.jpg"} for r in user_recipes]
    all_recipes = western + indo + user_formatted
    return random.sample(all_recipes, min(number, len(all_recipes)))

def get_recommendations_based_on_weather_and_region(weather, region, number=3):
    """Get recipe recommendations based on weather conditions and region."""
    if not weather:
        return get_random_recipes(number)

    condition = weather["weather_main"].lower()
    temp = weather["temp"]
    recommendations = []

    # Weather-based recommendation logic
    if "rain" in condition or temp < 20:
        # Suggest warm dishes like soups
        recommendations.extend(suggest_western_recipes_by_name("soup", number=1) or [])
        recommendations.extend(suggest_indonesian_recipes_by_name("soto", region=region, number=1) or [])
    elif temp > 30:
        # Suggest fresh dishes like salads
        recommendations.extend(suggest_western_recipes_by_name("salad", number=1) or [])
        recommendations.extend(suggest_indonesian_recipes_by_name("rujak", region=region, number=1) or [])
    else:
        # General recommendations
        recommendations.extend(get_random_recipes(1))

    # Region-based recommendation
    if region:
        region = region.lower()
        regional_recipes = suggest_indonesian_recipes_by_name("", region=region, number=1)
        recommendations.extend(regional_recipes)

    # Ensure uniqueness and limit to requested number
    seen = set()
    unique_recommendations = []
    for recipe in recommendations:
        if recipe["id"] not in seen:
            seen.add(recipe["id"])
            unique_recommendations.append(recipe)
    return unique_recommendations[:number]

def get_related_searches(weather=None):
    """Get related search suggestions, prioritized by popularity and weather."""
    searches = [
        {"query": "soto", "cuisine": "indonesian", "title": "Soto Ayam", "count": 10},
        {"query": "salad", "cuisine": "western", "title": "Fresh Salad", "count": 8},
        {"query": "rendang", "cuisine": "indonesian", "region": "Sumatra", "title": "Beef Rendang", "count": 12},
        {"query": "pasta", "cuisine": "western", "title": "Creamy Pasta", "count": 7},
        {"query": "gudeg", "cuisine": "indonesian", "region": "Java", "title": "Gudeg Jogja", "count": 9}
    ]
    if weather and "rain" in weather["weather_main"].lower():
        searches.insert(0, {"query": "soup", "cuisine": "western", "title": "Warm Soup", "count": 15})
    
    try:
        popular_searches = db.session.query(SearchHistory).order_by(SearchHistory.count.desc()).limit(5).all()
    except Exception as e:
        logging.error(f"Error querying SearchHistory: {e}")
        popular_searches = []
    
    for search in popular_searches:
        searches.append({
            "query": search.query,
            "cuisine": search.cuisine,
            "region": search.region,
            "title": search.query.title(),
            "count": search.count
        })
    
    unique_searches = {s["query"]: s for s in searches}.values()
    searches = sorted(unique_searches, key=lambda x: x["count"], reverse=True)[:5]
    for search in searches:
        search["is_popular"] = search["count"] > 10
    return searches

# Routes
@app.route("/")
def index():
    """Render the homepage with recipes, weather-based recommendations, and location-based suggestions."""
    weather = None
    recommendations = []
    search_results = []
    random_recipes = get_random_recipes(5)
    city = request.args.get("city", "Jakarta")
    query = request.args.get("query")
    cuisine = request.args.get("cuisine", "western")
    region = request.args.get("region", "All Regions")
    max_time = request.args.get("max_time")
    diet = request.args.get("diet")
    
    # Log search if query exists
    if query:
        try:
            existing = db.session.query(SearchHistory).filter_by(query=query, cuisine=cuisine, region=region).first()
            if existing:
                existing.count += 1
                existing.timestamp = datetime.utcnow()
            else:
                new_search = SearchHistory(query=query, cuisine=cuisine, region=region)
                db.session.add(new_search)
            db.session.commit()
        except Exception as e:
            logging.error(f"Error updating SearchHistory: {e}")
            flash("Failed to log search history.", "warning")
    
    # Default weather for Jakarta if no location is provided
    weather = get_weather(city)
    if weather:
        recommendations = get_recommendations_based_on_weather_and_region(weather, region)
    
    if query:
        if cuisine == "western":
            if max_time or diet:
                search_results = suggest_western_recipes_by_name(query, max_time=max_time, diet=diet)
            else:
                search_results = suggest_western_recipes_by_name(query)
        elif cuisine == "indonesian":
            search_results = suggest_indonesian_recipes_by_name(query, region=region)
        user_recipes = UserRecipe.query.filter(UserRecipe.title.ilike(f"%{query}%")).limit(5).all()
        search_results.extend([{"id": str(r.id), "title": r.title, "source": "user", "image": r.image or "/static/assets/default_recipe.jpg"} for r in user_recipes])
    
    related_searches = get_related_searches(weather)
    return render_template(
        "index.html",
        weather=weather,
        recommendations=recommendations,
        random_recipes=random_recipes,
        search_results=search_results,
        related_searches=related_searches,
        query=query
    )

@app.route("/api/weather-by-coords", methods=["POST"])
def weather_by_coords():
    """API endpoint to get weather by coordinates."""
    data = request.get_json()
    lat = data.get("lat")
    lon = data.get("lon")
    if not lat or not lon:
        return jsonify({"error": "Latitude and longitude are required"}), 400
    
    weather = get_weather_by_coords(lat, lon)
    if not weather:
        return jsonify({"error": "Failed to fetch weather data"}), 500
    
    return jsonify(weather)

@app.route("/api/recommend-by-location", methods=["POST"])
def recommend_by_location():
    """API endpoint to get recipe recommendations based on weather and region."""
    data = request.get_json()
    weather = data.get("weather")
    region = data.get("region")
    
    if not weather:
        return jsonify({"error": "Weather data is required"}), 400
    
    recommendations = get_recommendations_based_on_weather_and_region(weather, region)
    return jsonify(recommendations)

@app.route("/api/suggest")
def suggest():
    """API endpoint for recipe suggestions."""
    cuisine = request.args.get("cuisine", "western")
    search_type = request.args.get("type", "name")
    query = request.args.get("query", "")
    region = request.args.get("region", "All Regions")
    max_time = request.args.get("max_time")
    diet = request.args.get("diet")
    
    if query:
        try:
            existing = db.session.query(SearchHistory).filter_by(query=query, cuisine=cuisine, region=region).first()
            if existing:
                existing.count += 1
                existing.timestamp = datetime.utcnow()
            else:
                new_search = SearchHistory(query=query, cuisine=cuisine, region=region)
                db.session.add(new_search)
            db.session.commit()
        except Exception as e:
            logging.error(f"Error updating SearchHistory: {e}")
            flash("Failed to log search history.", "warning")

    if not query and (not region or region == "All Regions"):
        logging.warning("No query or region provided for search.")
        return jsonify({"error": "Please provide a search query or select a region."})

    recipes = []
    if cuisine == "western":
        if search_type == "name":
            recipes = suggest_western_recipes_by_name(query, max_time=max_time, diet=diet)
        elif search_type == "ingredients":
            ingredients = query.split(",")
            recipes = suggest_western_recipes_by_ingredients(ingredients, max_time=max_time, diet=diet)
    elif cuisine == "indonesian":
        recipes = suggest_indonesian_recipes_by_name(query, region=region)
    
    user_recipes = UserRecipe.query.filter(UserRecipe.title.ilike(f"%{query}%")).limit(5).all()
    recipes.extend([{"id": str(r.id), "title": r.title, "source": "user", "image": r.image or "/static/assets/default_recipe.jpg"} for r in user_recipes])
    
    logging.debug(f"Search results for query '{query}', cuisine '{cuisine}', region '{region}': {len(recipes)} recipes found.")
    return jsonify({"recipes": recipes})

@app.route("/recipe/<source>/<recipe_id>")
def recipe_detail(source, recipe_id):
    """Render detailed recipe page with comments and interactions."""
    recipe = None
    if source == "spoonacular":
        url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"
        params = {"apiKey": SPOONACULAR_KEY}
        try:
            response = requests.get(url, params=params, timeout=5)
            if response.status_code != 200:
                flash("Recipe not found.", "warning")
                return redirect(url_for("index"))
            data = response.json()
            recipe = {
                "id": str(data["id"]),
                "title": data["title"],
                "source": "spoonacular",
                "image": data.get("image", "/static/assets/default_recipe.jpg"),
                "ingredients": [ingredient["original"] for ingredient in data.get("extendedIngredients", [])],
                "instructions": bleach.clean(data.get("instructions", "No instructions available."), tags=['p', 'br', 'strong', 'em'])
            }
        except requests.RequestException:
            flash("Failed to fetch recipe.", "warning")
            return redirect(url_for("index"))
    elif source == "themealdb":
        url = f"{THEMEALDB_BASE_URL}/lookup.php?i={recipe_id}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                flash("Recipe not found.", "warning")
                return redirect(url_for("index"))
            data = response.json().get("meals", [{}])[0]
            if not isinstance(data, dict):
                flash("Invalid recipe data from TheMealDB.", "warning")
                return redirect(url_for("index"))
            ingredients = []
            for i in range(1, 21):
                ingredient = data.get(f"strIngredient{i}")
                measure = data.get(f"strMeasure{i}")
                if ingredient and ingredient.strip():
                    ingredients.append(f"{measure} {ingredient}".strip())
            recipe = {
                "id": str(recipe_id),
                "title": data.get("strMeal"),
                "source": "themealdb",
                "image": data.get("strMealThumb", "/static/assets/default_recipe.jpg"),
                "ingredients": ingredients,
                "instructions": bleach.clean(data.get("strInstructions", "No instructions available."), tags=['p', 'br', 'strong', 'em'])
            }
        except requests.RequestException:
            flash("Failed to fetch recipe.", "warning")
            return redirect(url_for("index"))
    elif source == "fallback":
        fallback_recipes = [
            {
                "id": "rendang",
                "title": "Beef Rendang",
                "source": "fallback",
                "image": "https://www.themealdb.com/images/media/meals/ypxrvg1515362401.jpg",
                "ingredients": ["500g beef", "400ml coconut milk", "2 lemongrass stalks", "5 kaffir lime leaves", "2 turmeric leaves", "10 shallots", "5 garlic cloves", "5 red chilies", "1 inch ginger", "1 inch galangal", "1 tsp turmeric powder", "Salt to taste"],
                "instructions": "Blend shallots, garlic, chilies, ginger, galangal, and turmeric into a paste. Cook the paste with lemongrass, lime leaves, and turmeric leaves until fragrant. Add beef and coconut milk, simmer for 3-4 hours until the sauce thickens and the beef is tender. Season with salt."
            },
            {
                "id": "soto",
                "title": "Soto Ayam",
                "source": "fallback",
                "image": "https://www.themealdb.com/images/media/meals/8mpqzz1508507655.jpg",
                "ingredients": ["500g chicken", "2L water", "2 lemongrass stalks", "3 kaffir lime leaves", "2 bay leaves", "5 shallots", "3 garlic cloves", "1 inch ginger", "1 tsp turmeric powder", "1 tsp coriander powder", "Salt to taste", "Vermicelli noodles", "Boiled eggs", "Lime wedges"],
                "instructions": "Boil chicken in water with lemongrass, lime leaves, and bay leaves. Blend shallots, garlic, ginger, turmeric, and coriander into a paste. Sauté the paste until fragrant, then add to the broth. Simmer for 30 minutes. Shred the chicken. Serve with vermicelli, boiled eggs, and lime wedges."
            },
            {
                "id": "gudeg",
                "title": "Gudeg Jogja",
                "source": "fallback",
                "image": "https://www.themealdb.com/images/media/meals/1529445893.jpg",
                "ingredients": ["1kg young jackfruit", "500ml coconut milk", "200g palm sugar", "5 shallots", "3 garlic cloves", "5 candlenuts", "1 tsp coriander powder", "2 bay leaves", "2 teak leaves", "Salt to taste"],
                "instructions": "Boil jackfruit until tender. Blend shallots, garlic, candlenuts, and coriander into a paste. Cook the paste with coconut milk, palm sugar, bay leaves, teak leaves, and jackfruit. Simmer for 4-5 hours until the jackfruit is soft and the sauce thickens. Season with salt."
            },
            {
                "id": "satay",
                "title": "Chicken Satay",
                "source": "fallback",
                "image": "https://www.themealdb.com/images/media/meals/1526418975.jpg",
                "ingredients": ["500g chicken", "2 tbsp soy sauce", "2 tbsp peanut butter", "1 tbsp lime juice", "5 shallots", "3 garlic cloves", "1 tsp turmeric powder", "1 tsp coriander powder", "Skewers"],
                "instructions": "Blend shallots, garlic, turmeric, and coriander into a paste. Marinate chicken with the paste, soy sauce, peanut butter, and lime juice for 1 hour. Skewer the chicken and grill until cooked. Serve with peanut sauce."
            },
            {
                "id": "nasi_goreng",
                "title": "Nasi Goreng",
                "source": "fallback",
                "image": "https://www.themealdb.com/images/media/meals/1529445893.jpg",
                "ingredients": ["2 cups cooked rice", "100g chicken", "2 eggs", "5 shallots", "3 garlic cloves", "2 red chilies", "1 tbsp soy sauce", "1 tbsp sweet soy sauce", "Salt to taste", "Fried shallots"],
                "instructions": "Blend shallots, garlic, and chilies into a paste. Sauté the paste until fragrant. Add chicken and cook until done. Push to the side, scramble the eggs. Add rice, soy sauce, sweet soy sauce, and salt. Stir-fry until mixed. Garnish with fried shallots."
            },
            {
                "id": "soto_banjar",
                "title": "Soto Banjar",
                "source": "fallback",
                "image": "https://www.themealdb.com/images/media/meals/8mpqzz1508507655.jpg",
                "region": "Kalimantan Selatan",
                "ingredients": ["500g chicken", "2L water", "2 lemongrass stalks", "3 kaffir lime leaves", "2 cloves", "2 star anise", "5 shallots", "3 garlic cloves", "1 inch ginger", "1 tsp turmeric powder", "Salt to taste", "Rice cakes", "Boiled eggs"],
                "instructions": "Boil chicken with lemongrass, lime leaves, cloves, and star anise. Blend shallots, garlic, ginger, and turmeric into a paste. Sauté the paste until fragrant, then add to the broth. Simmer for 30 minutes. Shred the chicken. Serve with rice cakes and boiled eggs."
            }
        ]
        recipe = next((r for r in fallback_recipes if r["id"] == recipe_id), None)
        if not recipe:
            flash("Recipe not found.", "warning")
            return redirect(url_for("index"))
    elif source == "user":
        user_recipe = UserRecipe.query.get(recipe_id)
        if not user_recipe:
            flash("Recipe not found.", "warning")
            return redirect(url_for("index"))
        recipe = {
            "id": str(user_recipe.id),
            "title": user_recipe.title,
            "source": "user",
            "image": user_recipe.image or "/static/assets/default_recipe.jpg",
            "ingredients": user_recipe.ingredients.split("\n"),
            "instructions": bleach.clean(user_recipe.instructions, tags=['p', 'br', 'strong', 'em'])
        }
    
    if not recipe:
        flash("Recipe not found.", "warning")
        return redirect(url_for("index"))

    page = request.args.get('page', 1, type=int)
    per_page = 5
    comments = Comment.query.filter_by(recipe_source=source, recipe_id=recipe_id).order_by(Comment.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    likes = Interaction.query.filter_by(recipe_source=source, recipe_id=recipe_id, interaction_type="like").count()
    saves = Interaction.query.filter_by(recipe_source=source, recipe_id=recipe_id, interaction_type="save").count()
    if source == "user":
        user_recipe = UserRecipe.query.get(recipe_id)
        if user_recipe:
            likes = user_recipe.likes
            saves = user_recipe.saves

    user_liked = False
    user_saved = False
    if current_user.is_authenticated:
        user_liked = Interaction.query.filter_by(
            user_id=current_user.id, recipe_source=source, recipe_id=recipe_id, interaction_type="like"
        ).first() is not None
        user_saved = Interaction.query.filter_by(
            user_id=current_user.id, recipe_source=source, recipe_id=recipe_id, interaction_type="save"
        ).first() is not None

    return render_template(
        "recipe.html",
        recipe=recipe,
        comments=comments,
        likes=likes,
        saves=saves,
        user_liked=user_liked,
        user_saved=user_saved
    )

@app.route("/interact", methods=["POST"])
@login_required
def interact():
    """Handle like/save interactions with proper synchronization."""
    source = request.form.get("source")
    recipe_id = request.form.get("recipe_id")
    action = request.form.get("action")
    
    # Prevent double-click by checking session-based lock
    session_key = f"interact_{current_user.id}_{source}_{recipe_id}_{action}"
    if session.get(session_key):
        return jsonify({"error": "Please wait before performing this action again."}), 429
    
    session[session_key] = True
    try:
        existing = Interaction.query.filter_by(
            user_id=current_user.id, recipe_source=source, recipe_id=recipe_id, interaction_type=action
        ).first()
        
        user_recipe = None
        if source == "user":
            user_recipe = UserRecipe.query.get(recipe_id)
            if not user_recipe:
                return jsonify({"error": "Recipe not found."}), 404
        
        if existing:
            # Undo the action
            db.session.delete(existing)
            if user_recipe:
                if action == "like":
                    user_recipe.likes = max(0, user_recipe.likes - 1)
                elif action == "save":
                    user_recipe.saves = max(0, user_recipe.saves - 1)
        else:
            # Perform the action
            interaction = Interaction(
                user_id=current_user.id, recipe_source=source, recipe_id=recipe_id, interaction_type=action
            )
            db.session.add(interaction)
            if user_recipe:
                if action == "like":
                    user_recipe.likes += 1
                elif action == "save":
                    user_recipe.saves += 1
        
        db.session.commit()

        likes = Interaction.query.filter_by(recipe_source=source, recipe_id=recipe_id, interaction_type="like").count()
        saves = Interaction.query.filter_by(recipe_source=source, recipe_id=recipe_id, interaction_type="save").count()
        if source == "user":
            user_recipe = UserRecipe.query.get(recipe_id)
            if user_recipe:
                likes = user_recipe.likes
                saves = user_recipe.saves

        user_liked = Interaction.query.filter_by(
            user_id=current_user.id, recipe_source=source, recipe_id=recipe_id, interaction_type="like"
        ).first() is not None
        user_saved = Interaction.query.filter_by(
            user_id=current_user.id, recipe_source=source, recipe_id=recipe_id, interaction_type="save"
        ).first() is not None

        return jsonify({
            "likes": likes,
            "saves": saves,
            "user_liked": user_liked,
            "user_saved": user_saved
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error during interaction: {e}")
        return jsonify({"error": "An error occurred while processing your request."}), 500
    finally:
        session.pop(session_key, None)

@app.route("/comment", methods=["POST"])
@login_required
def comment():
    """Handle recipe comments."""
    content = bleach.clean(request.form.get("content"), tags=['p', 'br', 'strong', 'em'])
    source = request.form.get("source")
    recipe_id = request.form.get("recipe_id")
    redirect_url = request.form.get("redirect_url")

    if not content:
        flash("Comment cannot be empty.", "warning")
        return redirect(redirect_url)

    new_comment = Comment(
        content=content,
        user_id=current_user.id,
        recipe_source=source,
        recipe_id=recipe_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(new_comment)
    db.session.commit()
    return redirect(redirect_url)

@app.route("/submit", methods=["GET", "POST"])
@login_required
def submit_recipe():
    """Handle recipe submission with image upload."""
    if request.method == "POST":
        title = request.form.get("title")
        ingredients = request.form.get("ingredients")
        instructions = bleach.clean(request.form.get("instructions"), tags=['p', 'br', 'strong', 'em'])
        cuisine = request.form.get("cuisine")
        region = request.form.get("region")
        image = request.files.get("image")

        if not title or not ingredients or not instructions or not cuisine:
            flash("Please fill out all required fields.", "warning")
            return redirect(url_for("submit_recipe"))

        image_filename = None
        if image and allowed_file(image.filename):
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            image_filename = f"/static/uploads/{filename}"

        recipe = UserRecipe(
            title=title,
            ingredients=ingredients,
            instructions=instructions,
            cuisine=cuisine,
            user_id=current_user.id,
            region=region if cuisine == "indonesian" else None,
            image=image_filename
        )
        db.session.add(recipe)
        db.session.commit()
        flash("Recipe submitted successfully!", "info")
        return redirect(url_for("index"))

    return render_template("submit_recipe.html")

@app.route("/profile")
@login_required
def profile():
    """Render user profile with liked recipes."""
    page = request.args.get('page', 1, type=int)
    per_page = 3
    liked = Interaction.query.filter_by(user_id=current_user.id, interaction_type="like").paginate(page=page, per_page=per_page, error_out=False)
    
    liked_recipes = []
    for interaction in liked.items:
        recipe = None
        if interaction.recipe_source == "spoonacular":
            url = f"https://api.spoonacular.com/recipes/{interaction.recipe_id}/information"
            params = {"apiKey": SPOONACULAR_KEY}
            try:
                response = requests.get(url, params=params, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    recipe = {
                        "id": str(data["id"]),
                        "title": data["title"],
                        "source": "spoonacular",
                        "image": data.get("image", "/static/assets/default_recipe.jpg"),
                        "url": url_for('recipe_detail', source='spoonacular', recipe_id=interaction.recipe_id)
                    }
            except requests.RequestException:
                continue
        elif interaction.recipe_source == "themealdb":
            url = f"{THEMEALDB_BASE_URL}/lookup.php?i={interaction.recipe_id}"
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json().get("meals", [{}])[0]
                    recipe = {
                        "id": str(interaction.recipe_id),
                        "title": data.get("strMeal", "TheMealDB Recipe"),
                        "source": "themealdb",
                        "image": data.get("strMealThumb", "/static/assets/default_recipe.jpg"),
                        "url": url_for('recipe_detail', source='themealdb', recipe_id=interaction.recipe_id)
                    }
            except requests.RequestException:
                continue
        elif interaction.recipe_source == "fallback":
            fallback_recipes = [
                {
                    "id": "rendang",
                    "title": "Beef Rendang",
                    "source": "fallback",
                    "image": "https://www.themealdb.com/images/media/meals/ypxrvg1515362401.jpg",
                },
                {
                    "id": "soto",
                    "title": "Soto Ayam",
                    "source": "fallback",
                    "image": "https://www.themealdb.com/images/media/meals/8mpqzz1508507655.jpg",
                },
                {
                    "id": "gudeg",
                    "title": "Gudeg Jogja",
                    "source": "fallback",
                    "image": "https://www.themealdb.com/images/media/meals/1529445893.jpg",
                },
                {
                    "id": "satay",
                    "title": "Chicken Satay",
                    "source": "fallback",
                    "image": "https://www.themealdb.com/images/media/meals/1526418975.jpg",
                },
                {
                    "id": "nasi_goreng",
                    "title": "Nasi Goreng",
                    "source": "fallback",
                    "image": "https://www.themealdb.com/images/media/meals/1529445893.jpg",
                },
                {
                    "id": "soto_banjar",
                    "title": "Soto Banjar",
                    "source": "fallback",
                    "image": "https://www.themealdb.com/images/media/meals/8mpqzz1508507655.jpg",
                }
            ]
            recipe_data = next((r for r in fallback_recipes if r["id"] == interaction.recipe_id), None)
            if recipe_data:
                recipe = {
                    "id": str(recipe_data["id"]),
                    "title": recipe_data["title"],
                    "source": "fallback",
                    "image": recipe_data["image"],
                    "url": url_for('recipe_detail', source='fallback', recipe_id=interaction.recipe_id)
                }
        else:  # user recipe
            user_recipe = UserRecipe.query.get(interaction.recipe_id)
            if user_recipe:
                recipe = {
                    "id": str(user_recipe.id),
                    "title": user_recipe.title,
                    "source": "user",
                    "image": user_recipe.image or "/static/assets/default_recipe.jpg",
                    "url": url_for('recipe_detail', source='user', recipe_id=interaction.recipe_id)
                }
        if recipe:
            liked_recipes.append({
                "recipe": recipe,
                "interaction": interaction
            })
    
    saved = Interaction.query.filter_by(user_id=current_user.id, interaction_type="save").all()
    return render_template("profile.html", user=current_user, liked=liked, liked_recipes=liked_recipes, saved=saved)

@app.route("/user_profile")
def user_profile():
    """Render user profile page."""
    return render_template("user_profile.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Logged in successfully!", "info")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.", "warning")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Handle user registration."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:
            flash("Passwords do not match.", "warning")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "warning")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "warning")
            return redirect(url_for("register"))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        flash("Registration successful! Please log in.", "info")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    """Handle user logout."""
    logout_user()
    flash("Logged out successfully!", "info")
    return redirect(url_for("index"))

if __name__ == "__main__":
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(debug=True)