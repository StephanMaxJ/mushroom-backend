# main.py - Complete with Authentication, Admin, Journal, and News Aggregation
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
import base64
import json
import feedparser
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
import time

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

# News aggregation configuration
MUSHROOM_RSS_FEEDS = [
    # Scientific journals and research
    "https://www.nature.com/subjects/mycology.rss",
    "https://www.sciencedaily.com/rss/plants_animals/mycology.xml",
    
    # Foraging and mushroom websites
    "https://www.foragerchef.com/feed/",
    "https://www.wildedible.com/feed",
    
    # Mushroom organizations
    "https://www.namyco.org/feed",
    
    # General science that includes fungi
    "https://feeds.feedburner.com/oreilly/radar",
]

# Reddit subreddits for mushroom content
MUSHROOM_SUBREDDITS = [
    'mycology', 'foraging', 'MushroomGrowers', 
    'mushroom_hunting', 'ShroomID', 'mushroomID'
]

# Keywords for filtering content
MUSHROOM_KEYWORDS = [
    "mushroom", "fungi", "mycology", "foraging", "porcini", "morel", 
    "chanterelle", "oyster mushroom", "shiitake", "wild mushroom",
    "mycorrhizae", "spore", "mycelium", "fungal", "edible fungi",
    "mushroom hunting", "mushroom identification", "mycologist"
]

SOUTH_AFRICAN_KEYWORDS = [
    "south africa", "cape town", "johannesburg", "durban", "african", 
    "southern africa", "fynbos", "indigenous mushroom"
]

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
    else:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        return sqlite3.connect(db_path)

def init_database():
    """Initialize database tables"""
    conn = get_database_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        # PostgreSQL tables
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
        
    else:
        # SQLite tables
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

def score_article_relevance(title: str, content: str) -> int:
    """Score article relevance to mushroom foraging (0-100)"""
    score = 0
    text = f"{title} {content}".lower()
    
    # Core mushroom terms
    for keyword in MUSHROOM_KEYWORDS:
        if keyword in text:
            score += 10
    
    # South African relevance bonus
    for keyword in SOUTH_AFRICAN_KEYWORDS:
        if keyword in text:
            score += 15
    
    # Foraging-specific terms
    foraging_terms = ["foraging", "wild", "hunting", "identify", "season", "habitat"]
    for term in foraging_terms:
        if term in text:
            score += 8
    
    # Scientific credibility
    science_terms = ["research", "study", "scientist", "university", "journal"]
    for term in science_terms:
        if term in text:
            score += 5
    
    return min(score, 100)

# News aggregation functions
async def fetch_rss_articles() -> List[dict]:
    """Fetch articles from RSS feeds"""
    articles = []
    
    for feed_url in MUSHROOM_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:5]:  # Limit per feed
                # Extract content
                content = ""
                if hasattr(entry, 'summary'):
                    content = entry.summary
                elif hasattr(entry, 'description'):
                    content = entry.description
                
                # Clean HTML tags
                if content:
                    soup = BeautifulSoup(content, 'html.parser')
                    content = soup.get_text()[:500] + "..."
                
                # Check relevance
                score = score_article_relevance(entry.title, content)
                if score >= 30:  # Minimum relevance threshold
                    
                    # Determine category
                    title_lower = entry.title.lower()
                    if any(word in title_lower for word in ["identify", "id", "species"]):
                        category = "identification"
                    elif any(word in title_lower for word in ["recipe", "cooking", "cook"]):
                        category = "recipes"
                    elif any(word in title_lower for word in ["location", "spot", "area", "where"]):
                        category = "locations"
                    else:
                        category = "general"
                    
                    articles.append({
                        "title": f"📰 {entry.title}",
                        "content": f"{content}\n\n🔗 [Read full article]({entry.link})",
                        "source": feed.title if hasattr(feed, 'title') else "RSS Feed",
                        "url": entry.link,
                        "published_at": datetime.now().isoformat(),
                        "category": category,
                        "relevance_score": score,
                        "post_type": "news"
                    })
                    
        except Exception as e:
            print(f"Error fetching RSS feed {feed_url}: {e}")
    
    return articles

async def fetch_reddit_posts() -> List[dict]:
    """Fetch mushroom posts from Reddit"""
    articles = []
    
    for subreddit in MUSHROOM_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=5"
            headers = {'User-Agent': 'ForagersBot/1.0'}
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                for post in data.get('data', {}).get('children', []):
                    post_data = post.get('data', {})
                    
                    # Filter for quality posts
                    if post_data.get('score', 0) > 20 and not post_data.get('is_self', False):
                        title = post_data.get('title', '')
                        content = post_data.get('selftext', '')
                        
                        # Check relevance
                        score = score_article_relevance(title, content)
                        if score >= 20:
                            articles.append({
                                "title": f"🔥 r/{subreddit}: {title}",
                                "content": f"{content[:300]}...\n\n💬 {post_data.get('num_comments', 0)} comments | 👍 {post_data.get('score', 0)} upvotes\n\n🔗 [View on Reddit](https://reddit.com{post_data.get('permalink')})",
                                "source": f"Reddit r/{subreddit}",
                                "url": f"https://reddit.com{post_data.get('permalink')}",
                                "published_at": datetime.fromtimestamp(post_data.get('created_utc', 0)).isoformat(),
                                "category": "general",
                                "relevance_score": score,
                                "post_type": "community"
                            })
            
            # Rate limiting
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"Reddit error for r/{subreddit}: {e}")
    
    return articles

async def create_weekly_digest() -> dict:
    """Create a weekly digest post"""
    try:
        today = datetime.now()
        
        # Fetch recent articles
        rss_articles = await fetch_rss_articles()
        reddit_posts = await fetch_reddit_posts()
        
        all_articles = rss_articles + reddit_posts
        
        # Sort by relevance score
        all_articles.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        top_articles = all_articles[:8]
        
        # Create digest content
        digest_content = f"""🍄 **Weekly Mushroom Digest** - {today.strftime('%B %d, %Y')}
        
Welcome to this week's roundup of mushroom news, research, and foraging updates!

## 📚 Featured Articles This Week:

"""
        
        for i, article in enumerate(top_articles, 1):
            digest_content += f"""
### {i}. {article['title'].replace('📰 ', '').replace('🔥 ', '')}
*Source: {article['source']}*

{article['content'][:200]}...

---
"""
        
        digest_content += f"""

## 🌍 Community Highlights
- Join our forum discussions on seasonal foraging
- Share your recent finds in the photo gallery
- Connect with local foraging groups

## 🔔 Reminders
- Always get expert verification before consuming wild mushrooms
- Check local regulations before foraging
- Practice sustainable harvesting

Happy foraging! 🍄🌿

*This digest is automatically generated from RSS feeds and community sources.*
"""
        
        return {
            "title": f"🍄 Weekly Mushroom Digest - {today.strftime('%B %d')}",
            "content": digest_content,
            "source": "Forager's Friend Auto-Digest",
            "category": "general",
            "published_at": today.isoformat(),
            "post_type": "digest"
        }
        
    except Exception as e:
        print(f"Digest creation error: {e}")
        return None

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

# Scheduled tasks
async def daily_news_aggregation():
    """Run daily to fetch and post new articles"""
    print("Running daily news aggregation...")
    
    try:
        # Fetch articles
        rss_articles = await fetch_rss_articles()
        reddit_posts = await fetch_reddit_posts()
        
        all_articles = rss_articles + reddit_posts
        
        # Post top articles (limit to prevent spam)
        top_articles = sorted(all_articles, key=lambda x: x.get('relevance_score', 0), reverse=True)[:5]
        
        for article in top_articles:
            await save_article_to_forum(article)
            await asyncio.sleep(1)  # Rate limiting
            
        print(f"Posted {len(top_articles)} articles to forum")
        
    except Exception as e:
        print(f"Daily aggregation error: {e}")

async def weekly_digest_creation():
    """Create weekly digest every Sunday"""
    print("Creating weekly digest...")
    
    try:
        digest = await create_weekly_digest()
        if digest:
            await save_article_to_forum(digest)
            print("Weekly digest created and posted")
            
    except Exception as e:
        print(f"Weekly digest error: {e}")

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
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE")
        new_users_today = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM journal_entries")
        total_entries = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT species_found) FROM journal_entries WHERE species_found IS NOT NULL AND species_found != ''")
        unique_species = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT location) FROM journal_entries WHERE location IS NOT NULL AND location != ''")
        unique_locations = cursor.fetchone()[0]
    else:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        active_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')")
        new_users_today = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM journal_entries")
        total_entries = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT species_found) FROM journal_entries WHERE species_found IS NOT NULL AND species_found != ''")
        unique_species = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT location) FROM journal_entries WHERE location IS NOT NULL AND location != ''")
        unique_locations = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "admin_users": admin_users,
        "new_users_today": new_users_today,
        "total_entries": total_entries,
        "unique_species": unique_species,
        "unique_locations": unique_locations
    }

# Admin Journal Viewing Endpoints
@app.get("/admin/journal-entries")
async def get_all_journal_entries(
    user_id: int = Query(None),
    search: str = Query(None),
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Base query
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        query = '''
            SELECT je.id, je.user_id, je.date, je.location, je.species_found, 
                   je.temperature, je.humidity, je.rainfall, je.wind_speed,
                   je.entry_text, je.images, je.created_at, u.username
            FROM journal_entries je
            JOIN users u ON je.user_id = u.id
        '''
        params = []
        conditions = []
        
        if user_id:
            conditions.append("je.user_id = %s")
            params.append(user_id)
        
        if search:
            conditions.append("(je.species_found ILIKE %s OR je.location ILIKE %s OR je.entry_text ILIKE %s OR u.username ILIKE %s)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param, search_param])
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY je.created_at DESC LIMIT 100"
        cursor.execute(query, params)
    else:
        query = '''
            SELECT je.id, je.user_id, je.date, je.location, je.species_found, 
                   je.temperature, je.humidity, je.rainfall, je.wind_speed,
                   je.entry_text, je.images, je.created_at, u.username
            FROM journal_entries je
            JOIN users u ON je.user_id = u.id
        '''
        params = []
        conditions = []
        
        if user_id:
            conditions.append("je.user_id = ?")
            params.append(user_id)
        
        if search:
            conditions.append("(je.species_found LIKE ? OR je.location LIKE ? OR je.entry_text LIKE ? OR u.username LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param, search_param])
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY je.created_at DESC LIMIT 100"
        cursor.execute(query, params)
    
    entries = cursor.fetchall()
    conn.close()
    
    return {
        "entries": [
            {
                "id": entry[0],
                "user_id": entry[1],
                "date": entry[2],
                "location": entry[3],
                "species_found": entry[4] or "",
                "temperature": entry[5],
                "humidity": entry[6],
                "rainfall": entry[7],
                "wind_speed": entry[8],
                "entry_text": entry[9],
                "images": json.loads(entry[10]) if entry[10] else [],
                "created_at": entry[11],
                "username": entry[12]
            }
            for entry in entries
        ]
    }

@app.get("/admin/user-journals/{user_id}")
async def get_user_journals(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Get user info
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("SELECT username, email FROM users WHERE id = %s", (user_id,))
    else:
        cursor.execute("SELECT username, email FROM users WHERE id = ?", (user_id,))
    
    user_info = cursor.fetchone()
    if not user_info:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user's journal entries
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            SELECT id, date, location, species_found, temperature, humidity, 
                   rainfall, wind_speed, entry_text, images, created_at
            FROM journal_entries 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT id, date, location, species_found, temperature, humidity, 
                   rainfall, wind_speed, entry_text, images, created_at
            FROM journal_entries 
            WHERE user_id = ? 
            ORDER BY created_at DESC
        ''', (user_id,))
    
    entries = cursor.fetchall()
    conn.close()
    
    return {
        "user": {
            "id": user_id,
            "username": user_info[0],
            "email": user_info[1]
        },
        "entries": [
            {
                "id": entry[0],
                "date": entry[1],
                "location": entry[2],
                "species_found": entry[3] or "",
                "temperature": entry[4],
                "humidity": entry[5],
                "rainfall": entry[6],
                "wind_speed": entry[7],
                "entry_text": entry[8],
                "images": json.loads(entry[9]) if entry[9] else [],
                "created_at": entry[10]
            }
            for entry in entries
        ]
    }

@app.delete("/admin/journal-entries/{entry_id}")
async def delete_journal_entry_admin(entry_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Check if entry exists
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("SELECT id FROM journal_entries WHERE id = %s", (entry_id,))
    else:
        cursor.execute("SELECT id FROM journal_entries WHERE id = ?", (entry_id,))
    
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Journal entry not found")
    
    # Delete the entry
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("DELETE FROM journal_entries WHERE id = %s", (entry_id,))
    else:
        cursor.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
    
    conn.commit()
    conn.close()
    
    return {"message": "Journal entry deleted successfully"}

@app.get("/admin/analytics")
async def get_admin_analytics(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Most active users
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            SELECT u.username, COUNT(je.id) as entry_count
            FROM users u
            LEFT JOIN journal_entries je ON u.id = je.user_id
            GROUP BY u.id, u.username
            ORDER BY entry_count DESC
            LIMIT 10
        ''')
    else:
        cursor.execute('''
            SELECT u.username, COUNT(je.id) as entry_count
            FROM users u
            LEFT JOIN journal_entries je ON u.id = je.user_id
            GROUP BY u.id, u.username
            ORDER BY entry_count DESC
            LIMIT 10
        ''')
    
    most_active_users = []
    for row in cursor.fetchall():
        most_active_users.append({
            "username": row[0],
            "entry_count": row[1]
        })
    
    # Popular species
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            SELECT species_found, COUNT(*) as count
            FROM journal_entries
            WHERE species_found IS NOT NULL AND species_found != ''
            GROUP BY species_found
            ORDER BY count DESC
            LIMIT 10
        ''')
    else:
        cursor.execute('''
            SELECT species_found, COUNT(*) as count
            FROM journal_entries
            WHERE species_found IS NOT NULL AND species_found != ''
            GROUP BY species_found
            ORDER BY count DESC
            LIMIT 10
        ''')
    
    popular_species = []
    for row in cursor.fetchall():
        popular_species.append({
            "species": row[0],
            "count": row[1]
        })
    
    # Top locations
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            SELECT location, COUNT(*) as count
            FROM journal_entries
            WHERE location IS NOT NULL AND location != ''
            GROUP BY location
            ORDER BY count DESC
            LIMIT 10
        ''')
    else:
        cursor.execute('''
            SELECT location, COUNT(*) as count
            FROM journal_entries
            WHERE location IS NOT NULL AND location != ''
            GROUP BY location
            ORDER BY count DESC
            LIMIT 10
        ''')
    
    top_locations = []
    for row in cursor.fetchall():
        top_locations.append({
            "location": row[0],
            "count": row[1]
        })
    
    # Recent activity
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            SELECT je.species_found, je.location, je.date, u.username, je.created_at
            FROM journal_entries je
            JOIN users u ON je.user_id = u.id
            ORDER BY je.created_at DESC
            LIMIT 10
        ''')
    else:
        cursor.execute('''
            SELECT je.species_found, je.location, je.date, u.username, je.created_at
            FROM journal_entries je
            JOIN users u ON je.user_id = u.id
            ORDER BY je.created_at DESC
            LIMIT 10
        ''')
    
    recent_activity = []
    for row in cursor.fetchall():
        recent_activity.append({
            "species": row[0] or "Unknown",
            "location": row[1],
            "date": row[2],
            "username": row[3],
            "created_at": row[4]
        })
    
    conn.close()
    
    return {
        "most_active_users": most_active_users,
        "popular_species": popular_species,
        "top_locations": top_locations,
        "recent_activity": recent_activity
    }

# Forum routes
@app.get("/forum/posts")
async def get_forum_posts(category: str = Query(None), current_user: dict = Depends(get_current_user)):
    """Get forum posts including auto-generated news"""
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
            if category and category != 'all':
                cursor.execute('''
                    SELECT id, title, content, category, author, source_url, auto_generated, 
                           created_at, replies_count, post_type
                    FROM forum_posts 
                    WHERE category = %s 
                    ORDER BY created_at DESC 
                    LIMIT 50
                ''', (category,))
            else:
                cursor.execute('''
                    SELECT id, title, content, category, author, source_url, auto_generated, 
                           created_at, replies_count, post_type
                    FROM forum_posts 
                    ORDER BY created_at DESC 
                    LIMIT 50
                ''')
        else:
            if category and category != 'all':
                cursor.execute('''
                    SELECT id, title, content, category, author, source_url, auto_generated, 
                           created_at, replies_count, post_type
                    FROM forum_posts 
                    WHERE category = ? 
                    ORDER BY created_at DESC 
                    LIMIT 50
                ''', (category,))
            else:
                cursor.execute('''
                    SELECT id, title, content, category, author, source_url, auto_generated, 
                           created_at, replies_count, post_type
                    FROM forum_posts 
                    ORDER BY created_at DESC 
                    LIMIT 50
                ''')
        
        posts = cursor.fetchall()
        
        return {
            "posts": [
                {
                    "id": post[0],
                    "title": post[1],
                    "content": post[2],
                    "category": post[3],
                    "author": post[4],
                    "source_url": post[5],
                    "auto_generated": bool(post[6]),
                    "created_at": post[7],
                    "replies": post[8],
                    "post_type": post[9] if len(post) > 9 else "user",
                    "images": []  # Placeholder for images
                }
                for post in posts
            ]
        }
        
    except Exception as e:
        print(f"Error loading forum posts: {e}")
        # Return empty posts if database not ready
        return {"posts": []}
    finally:
        conn.close()

@app.post("/forum/posts")
async def create_forum_post(post: ForumPost, current_user: dict = Depends(get_current_user)):
    """Create a new forum post"""
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
            cursor.execute('''
                INSERT INTO forum_posts (title, content, category, author, auto_generated, created_at, post_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (post.title, post.content, post.category, current_user["username"], False, datetime.now().isoformat(), "user"))
        else:
            cursor.execute('''
                INSERT INTO forum_posts (title, content, category, author, auto_generated, created_at, post_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (post.title, post.content, post.category, current_user["username"], 0, datetime.now().isoformat(), "user"))
        
        conn.commit()
        return {"message": "Post created successfully"}
        
    except Exception as e:
        print(f"Error creating forum post: {e}")
        raise HTTPException(status_code=500, detail="Failed to create post")
    finally:
        conn.close()

# News aggregation admin endpoints
@app.post("/admin/news/fetch-now")
async def fetch_news_now(current_user: dict = Depends(get_current_user)):
    """Manually trigger news fetching (admin only)"""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        await daily_news_aggregation()
        return {"message": "News aggregation completed", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"News fetch failed: {str(e)}")

@app.post("/admin/news/create-digest")
async def create_digest_now(current_user: dict = Depends(get_current_user)):
    """Manually create weekly digest (admin only)"""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        await weekly_digest_creation()
        return {"message": "Weekly digest created", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Digest creation failed: {str(e)}")

# Journal routes
@app.post("/journal/entries")
async def create_journal_entry(entry: JournalEntry, current_user: dict = Depends(get_current_user)):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    images_json = json.dumps(entry.images) if entry.images else None
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            INSERT INTO journal_entries 
            (user_id, date, location, temperature, humidity, rainfall, wind_speed, species_found, entry_text, images)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (current_user["id"], entry.date, entry.location, entry.temperature, entry.humidity,
              entry.rainfall, entry.wind_speed, entry.species_found, entry.entry_text, images_json))
    else:
        cursor.execute('''
            INSERT INTO journal_entries 
            (user_id, date, location, temperature, humidity, rainfall, wind_speed, species_found, entry_text, images)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (current_user["id"], entry.date, entry.location, entry.temperature, entry.humidity,
              entry.rainfall, entry.wind_speed, entry.species_found, entry.entry_text, images_json))
    
    conn.commit()
    conn.close()
    
    return {"message": "Journal entry created successfully"}

@app.get("/journal/entries")
async def get_journal_entries(current_user: dict = Depends(get_current_user)):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("SELECT * FROM journal_entries WHERE user_id = %s ORDER BY created_at DESC", 
                      (current_user["id"],))
    else:
        cursor.execute("SELECT * FROM journal_entries WHERE user_id = ? ORDER BY created_at DESC", 
                      (current_user["id"],))
    
    entries = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": entry[0],
            "date": entry[2],
            "location": entry[3],
            "temperature": entry[4],
            "humidity": entry[5],
            "rainfall": entry[6],
            "wind_speed": entry[7],
            "species_found": entry[8],
            "entry_text": entry[9],
            "images": json.loads(entry[10]) if entry[10] else [],
            "created_at": entry[11]
        }
        for entry in entries
    ]

@app.get("/journal/stats")
async def get_journal_stats(current_user: dict = Depends(get_current_user)):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute("SELECT * FROM journal_entries WHERE user_id = %s", (current_user["id"],))
    else:
        cursor.execute("SELECT * FROM journal_entries WHERE user_id = ?", (current_user["id"],))
    
    entries = cursor.fetchall()
    conn.close()
    
    total_entries = len(entries)
    species = set()
    locations = set()
    total_photos = 0
    
    for entry in entries:
        if entry[8]:  # species_found
            species.update(s.strip().lower() for s in entry[8].split(','))
        if entry[3]:  # location
            locations.add(entry[3].lower())
        if entry[10]:  # images
            try:
                images = json.loads(entry[10])
                total_photos += len(images) if isinstance(images, list) else 1
            except:
                pass
    
    return {
        "total_entries": total_entries,
        "unique_species": len(species),
        "unique_locations": len(locations),
        "total_photos": total_photos
    }

# Health check
@app.get("/health")
def health_check():
    return {"status": "healthy", "environment": ENVIRONMENT}

# Initialize scheduler
scheduler = AsyncIOScheduler()

# Startup event
@app.on_event("startup")
async def startup_event():
    init_database()
    
    # Schedule news aggregation
    scheduler.add_job(daily_news_aggregation, 'cron', hour=8, minute=0)  # Daily at 8 AM
    scheduler.add_job(weekly_digest_creation, 'cron', day_of_week=0, hour=9, minute=0)  # Sundays at 9 AM
    
    scheduler.start()
    print("News aggregation scheduler started")

# For Render deployment
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
