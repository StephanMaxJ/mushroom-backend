# main.py - Fixed for Render Deployment
import os
from fastapi import FastAPI, HTTPException, Query, Depends, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
import requests
from datetime import datetime, timedelta
import jwt
import bcrypt
import sqlite3
from typing import List, Optional
import json
import asyncio

# Environment Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-change-in-production")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mushroom_app.db")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

app = FastAPI(
    title="Mushroom Foraging API",
    description="API for mushroom identification, foraging journal, and community",
    version="1.0.0"
)

# CORS Configuration
if ENVIRONMENT == "production":
    allowed_origins = [
        FRONTEND_URL,
        "https://www.foragersfriend.info", 
        "https://foragersfriend.info",      
        "https://*.onrender.com",
        "https://*.netlify.app",
        "https://*.vercel.app"
    ]
else:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Your existing mushroom profiles
MUSHROOM_PROFILES = {
    "porcini": {"temp_range": (12, 28), "humidity_min": 70, "rain_min": 0.1, "rain_max": 80, "wind_max": 16},
    "pine_rings": {"temp_range": (10, 22), "humidity_min": 65, "rain_min": 0.1, "rain_max": 80, "wind_max": 16},
    "poplar_boletes": {"temp_range": (10, 23), "humidity_min": 60, "rain_min": 0.1, "rain_max": 35, "wind_max": 16},
    "agaricus": {"temp_range": (14, 26), "humidity_min": 65, "rain_min": 0.8, "rain_max": 50, "wind_max": 11},
    "white_parasols": {"temp_range": (13, 28), "humidity_min": 60, "rain_min": 0, "rain_max": 30, "wind_max": 12},
    "wood_blewits": {"temp_range": (4, 8), "humidity_min": 70, "rain_min": 5, "rain_max": 50, "wind_max": 12},
    "morels": {"temp_range": (12, 21), "humidity_min": 70, "rain_min": 10, "rain_max": 50, "wind_max": 4},
    "blushers": {"temp_range": (8, 26), "humidity_min": 60, "rain_min": 0.1, "rain_max": 35, "wind_max": 16},
    "slippery_jills": {"temp_range": (9, 24), "humidity_min": 65, "rain_min": 0.5, "rain_max": 30, "wind_max": 15},
    "weeping_bolete": {"temp_range": (9, 23), "humidity_min": 60, "rain_min": 0.5, "rain_max": 25, "wind_max": 15},
    "bovine_bolete": {"temp_range": (9, 22), "humidity_min": 60, "rain_min": 0.5, "rain_max": 28, "wind_max": 15},
    "chicken_of_the_woods": {"temp_range": (23, 30), "humidity_min": 70, "rain_min": 10, "rain_max": 40, "wind_max": 10},
    "termitomyces": {"temp_range": (20, 32), "humidity_min": 80, "rain_min": 15, "rain_max": 50, "wind_max": 4}
}

# Database functions
def get_database_connection():
    """Get database connection - supports both SQLite and PostgreSQL"""
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        try:
            import psycopg2
            from urllib.parse import urlparse
            result = urlparse(DATABASE_URL)
            return psycopg2.connect(
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port
            )
        except ImportError:
            print("Warning: psycopg2 not installed. Falling back to SQLite.")
            return sqlite3.connect("mushroom_app.db")
    else:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        return sqlite3.connect(db_path)

def init_database():
    """Initialize database tables"""
    conn = get_database_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        # PostgreSQL tables
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(100),
                    bio TEXT,
                    location VARCHAR(100),
                    role VARCHAR(20) DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS journal_entries (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    date DATE NOT NULL,
                    location VARCHAR(200) NOT NULL,
                    temperature FLOAT,
                    humidity FLOAT,
                    rainfall FLOAT,
                    wind_speed FLOAT,
                    species_found TEXT,
                    entry_text TEXT NOT NULL,
                    images TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS forum_posts (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(300) NOT NULL,
                    content TEXT NOT NULL,
                    category VARCHAR(50) DEFAULT 'general',
                    author VARCHAR(100) NOT NULL,
                    source_url TEXT,
                    auto_generated BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    replies_count INTEGER DEFAULT 0,
                    post_type VARCHAR(50) DEFAULT 'user'
                )
            ''')
            
            # Insert admin user
            password_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, full_name, role)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            ''', ("admin", "admin@mushroomapp.com", password_hash, "Administrator", "admin"))
        except Exception as e:
            print(f"PostgreSQL setup failed, falling back to SQLite: {e}")
            # Fallback to SQLite
            conn.close()
            conn = sqlite3.connect("mushroom_app.db")
            cursor = conn.cursor()
    
    # SQLite tables (fallback or primary)
    if not DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                bio TEXT,
                location TEXT,
                role TEXT DEFAULT 'user',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT NOT NULL,
                location TEXT NOT NULL,
                temperature REAL,
                humidity REAL,
                rainfall REAL,
                wind_speed REAL,
                species_found TEXT,
                entry_text TEXT NOT NULL,
                images TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS forum_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                author TEXT NOT NULL,
                source_url TEXT,
                auto_generated INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                replies_count INTEGER DEFAULT 0,
                post_type TEXT DEFAULT 'user'
            )
        ''')
        
        # Insert admin user
        password_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute('''
            INSERT OR IGNORE INTO users (username, email, password_hash, full_name, role)
            VALUES (?, ?, ?, ?, ?)
        ''', ("admin", "admin@mushroomapp.com", password_hash, "Administrator", "admin"))
    
    conn.commit()
    conn.close()

# Models
class User(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class JournalEntry(BaseModel):
    date: str
    location: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    rainfall: Optional[float] = None
    wind_speed: Optional[float] = None
    species_found: Optional[str] = None
    entry_text: str
    images: Optional[List[dict]] = None

class ForumPost(BaseModel):
    title: str
    content: str
    category: str

# Authentication functions
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except jwt.PyJWTError:
        return None

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    username = verify_token(credentials.credentials)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    else:
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user[0],
        "username": user[1],
        "email": user[2],
        "full_name": user[4],
        "bio": user[5],
        "location": user[6],
        "role": user[7],
        "is_active": user[8],
        "created_at": user[9]
    }

# Utility functions
def get_season():
    month = datetime.utcnow().month
    if 12 <= month <= 2:
        return "Summer 🌞"
    elif 3 <= month <= 5:
        return "Autumn 🍂"
    elif 6 <= month <= 8:
        return "Winter 🌧️"
    else:
        return "Spring 🌸"

def average(values):
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else 0

# News aggregation functions (simplified for deployment)
def score_article_relevance(title: str, content: str) -> int:
    """Score article relevance to mushroom foraging (0-100)"""
    mushroom_keywords = [
        "mushroom", "fungi", "mycology", "foraging", "porcini", "morel", 
        "chanterelle", "oyster mushroom", "shiitake", "wild mushroom"
    ]
    
    score = 0
    text = f"{title} {content}".lower()
    
    for keyword in mushroom_keywords:
        if keyword in text:
            score += 15
    
    return min(score, 100)

async def fetch_simple_news() -> List[dict]:
    """Simplified news fetching for deployment"""
    articles = []
    
    try:
        # Simple Reddit API call (no dependencies)
        url = "https://www.reddit.com/r/mycology/hot.json?limit=5"
        headers = {'User-Agent': 'ForagersBot/1.0'}
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            for post in data.get('data', {}).get('children', []):
                post_data = post.get('data', {})
                
                if post_data.get('score', 0) > 20:
                    title = post_data.get('title', '')
                    content = post_data.get('selftext', '')
                    
                    score = score_article_relevance(title, content)
                    if score >= 20:
                        articles.append({
                            "title": f"🔥 Reddit: {title}",
                            "content": f"{content[:300]}...\n\n💬 {post_data.get('num_comments', 0)} comments\n\n🔗 [View on Reddit](https://reddit.com{post_data.get('permalink')})",
                            "source": "Reddit r/mycology",
                            "url": f"https://reddit.com{post_data.get('permalink')}",
                            "published_at": datetime.now().isoformat(),
                            "category": "general",
                            "post_type": "community"
                        })
        
        await asyncio.sleep(1)  # Rate limiting
        
    except Exception as e:
        print(f"News fetch error: {e}")
    
    return articles

async def save_article_to_forum(article_data: dict, author_username: str = "ForagersBot"):
    """Save article as forum post"""
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
            cursor.execute('''
                INSERT INTO forum_posts (title, content, category, author, source_url, auto_generated, created_at, post_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                article_data['title'],
                article_data['content'],
                article_data['category'],
                author_username,
                article_data.get('url', ''),
                True,
                article_data['published_at'],
                article_data.get('post_type', 'news')
            ))
        else:
            cursor.execute('''
                INSERT INTO forum_posts (title, content, category, author, source_url, auto_generated, created_at, post_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                article_data['title'],
                article_data['content'], 
                article_data['category'],
                author_username,
                article_data.get('url', ''),
                1,
                article_data['published_at'],
                article_data.get('post_type', 'news')
            ))
        
        conn.commit()
        print(f"Saved article: {article_data['title']}")
        
    except Exception as e:
        print(f"Error saving article: {e}")
    finally:
        conn.close()

# Routes - Your existing weather check endpoint
@app.get("/check")
def check_conditions(lat: float = Query(...), lon: float = Query(...), current_user: dict = Depends(get_current_user)):
    """Weather conditions check"""
    weatherapi_key = "b5c1991aa27149c881e173752250505"
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=6)

    # Open-Meteo historical data
    open_meteo_url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}&start_date={start_date}&end_date={today}"
        f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m&timezone=auto"
    )
    
    try:
        meteo_response = requests.get(open_meteo_url, timeout=10)
        if meteo_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Open-Meteo data error")
        meteo_data = meteo_response.json().get("hourly", {})
    except requests.RequestException:
        # Fallback values if API fails
        meteo_data = {"temperature_2m": [15], "relative_humidity_2m": [70], "wind_speed_10m": [10]}

    avg_temp = average(meteo_data.get("temperature_2m", []))
    avg_humidity = average(meteo_data.get("relative_humidity_2m", []))
    avg_wind = average(meteo_data.get("wind_speed_10m", []))

    # WeatherAPI rainfall
    rain_values = []
    for i in range(7):
        date = today - timedelta(days=i)
        try:
            url = f"http://api.weatherapi.com/v1/history.json?key={weatherapi_key}&q={lat},{lon}&dt={date}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                day_data = response.json().get("forecast", {}).get("forecastday", [{}])[0].get("day", {})
                rain_values.append(day_data.get("totalprecip_mm", 0))
        except requests.RequestException:
            rain_values.append(0)  # Fallback

    avg_rain = average(rain_values) if rain_values else 0

    # Foraging conditions
    if avg_temp >= 19 and avg_rain <= 40 and avg_humidity >= 90 and avg_wind <= 8:
        quality = "🍄‍🟫 Perfect day, there should be lots out"
    elif avg_temp >= 15 and avg_rain <= 20 and avg_humidity >= 70 and avg_wind <= 12:
        quality = "✅ Good day, go check your spots you may get lucky"
    elif avg_temp >= 12 and avg_rain <= 10 and avg_humidity >= 60 and avg_wind <= 15:
        quality = "❔ Average day, some mushrooms around but not much"
    else:
        quality = "❌ Not a good day, you could still check microclimates you know of"

    # Mushroom recommendations
    recommended = []
    for name, profile in MUSHROOM_PROFILES.items():
        t_min, t_max = profile["temp_range"]
        if (
            t_min <= avg_temp <= t_max and
            profile["humidity_min"] <= avg_humidity and
            profile["rain_min"] <= avg_rain <= profile["rain_max"] and
            avg_wind <= profile["wind_max"]
        ):
            recommended.append(name)

    # Current forecast
    try:
        forecast_url = f"http://api.weatherapi.com/v1/current.json?key={weatherapi_key}&q={lat},{lon}"
        forecast_response = requests.get(forecast_url, timeout=10)
        current = forecast_response.json().get("current", {}) if forecast_response.status_code == 200 else {}
    except requests.RequestException:
        current = {}

    return {
        "location": {"lat": lat, "lon": lon},
        "season": get_season(),
        "foraging_quality": quality,
        "avg_temperature": round(avg_temp, 1),
        "avg_precipitation": round(avg_rain, 1),
        "avg_humidity": round(avg_humidity, 1),
        "avg_wind_speed": round(avg_wind, 1),
        "forecast_temperature": current.get("temp_c"),
        "forecast_humidity": current.get("humidity"),
        "forecast_precipitation": current.get("precip_mm", 0),
        "forecast_wind_speed": current.get("wind_kph"),
        "recommended_mushrooms": recommended,
        "user": current_user["username"]
    }

# Authentication routes
@app.post("/signup")
async def signup(user: UserCreate):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Check if user exists
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("SELECT username FROM users WHERE username = %s OR email = %s", 
                      (user.username, user.email))
    else:
        cursor.execute("SELECT username FROM users WHERE username = ? OR email = ?", 
                      (user.username, user.email))
    
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username or email already registered")
    
    # Hash password and create user
    password_hash = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name)
            VALUES (%s, %s, %s, %s)
        ''', (user.username, user.email, password_hash, user.full_name))
    else:
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name)
            VALUES (?, ?, ?, ?)
        ''', (user.username, user.email, password_hash, user.full_name))
    
    conn.commit()
    conn.close()
    
    access_token = create_access_token(data={"sub": user.username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username
    }

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("SELECT username, password_hash FROM users WHERE username = %s", 
                      (form_data.username,))
    else:
        cursor.execute("SELECT username, password_hash FROM users WHERE username = ?", 
                      (form_data.username,))
    
    user = cursor.fetchone()
    conn.close()
    
    if not user or not bcrypt.checkpw(form_data.password.encode('utf-8'), user[1].encode('utf-8')):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(data={"sub": user[0]})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user[0]
    }

# User profile routes
@app.get("/user/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    return current_user

@app.put("/user/profile")
async def update_user_profile(user_update: UserUpdate, current_user: dict = Depends(get_current_user)):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            UPDATE users SET email = %s, full_name = %s, bio = %s, location = %s
            WHERE username = %s
        ''', (user_update.email, user_update.full_name, user_update.bio, 
              user_update.location, current_user["username"]))
    else:
        cursor.execute('''
            UPDATE users SET email = ?, full_name = ?, bio = ?, location = ?
            WHERE username = ?
        ''', (user_update.email, user_update.full_name, user_update.bio, 
              user_update.location, current_user["username"]))
    
    conn.commit()
    conn.close()
    
    return {"message": "Profile updated successfully"}

@app.post("/user/change-password")
async def change_password(password_data: PasswordChange, current_user: dict = Depends(get_current_user)):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Verify current password
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("SELECT password_hash FROM users WHERE username = %s", (current_user["username"],))
    else:
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (current_user["username"],))
    
    user = cursor.fetchone()
    if not user or not bcrypt.checkpw(password_data.current_password.encode('utf-8'), user[0].encode('utf-8')):
        conn.close()
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Update password
    new_password_hash = bcrypt.hashpw(password_data.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("UPDATE users SET password_hash = %s WHERE username = %s", 
                      (new_password_hash, current_user["username"]))
    else:
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", 
                      (new_password_hash, current_user["username"]))
    
    conn.commit()
    conn.close()
    
    return {"message": "Password changed successfully"}

# Admin routes
@app.get("/admin/check")
async def check_admin(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"is_admin": True}

@app.get("/admin/users")
async def get_all_users(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Get users with journal count
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            SELECT u.id, u.username, u.email, u.full_name, u.role, u.is_active, u.created_at,
                   COUNT(j.id) as journal_count
            FROM users u
            LEFT JOIN journal_entries j ON u.id = j.user_id
            GROUP BY u.id, u.username, u.email, u.full_name, u.role, u.is_active, u.created_at
            ORDER BY u.created_at DESC
        ''')
    else:
        cursor.execute('''
            SELECT u.id, u.username, u.email, u.full_name, u.role, u.is_active, u.created_at,
                   COUNT(j.id) as journal_count
            FROM users u
            LEFT JOIN journal_entries j ON u.id = j.user_id
            GROUP BY u.id, u.username, u.email, u.full_name, u.role, u.is_active, u.created_at
            ORDER BY u.created_at DESC
        ''')
    
    users = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": user[0],
            "username": user[1],
            "email": user[2],
            "full_name": user[3],
            "role": user[4],
            "is_active": user[5],
            "created_at": user[6],
            "journal_count": user[7]
        }
        for user in users
    ]

@app.get("/admin/stats")
async def get_admin_stats(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Get user statistics
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = true")
        active_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM
