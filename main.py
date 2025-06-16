# main.py - Fixed and Working Version
import os
from fastapi import FastAPI, HTTPException, Query, Depends, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import secrets
import requests
import json
import sqlite3
from passlib.context import CryptContext
import jwt
from contextlib import asynccontextmanager

# Try to import PostgreSQL adapter
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    print("PostgreSQL adapter not available, using SQLite")

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", None)
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security
security = HTTPBearer()

# Weather API configuration
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# Database connection
def get_db_connection():
    if DATABASE_URL and POSTGRES_AVAILABLE:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    else:
        conn = sqlite3.connect('foragersfriend.db')
        conn.row_factory = sqlite3.Row
        return conn

# Pydantic models
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class User(BaseModel):
    id: int
    username: str
    email: str
    role: str = "user"
    created_at: Optional[datetime] = None

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    favorite_mushroom: Optional[str] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class JournalEntryCreate(BaseModel):
    date: str
    location: str
    species_found: str = ""
    quantity: str = ""
    weather_conditions: str = ""
    temperature: str = ""
    humidity: str = ""
    entry_text: str
    photo_url: Optional[str] = None

class WeatherRequest(BaseModel):
    lat: float
    lon: float

class ForumPost(BaseModel):
    title: str
    content: str
    category: str
    author: str
    image_url: Optional[str] = None

# Startup event
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    init_db()
    print("Database initialized")
    yield
    print("Shutting down")

# Create FastAPI app
app = FastAPI(lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.foragersfriend.info", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database initialization
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(255),
                location VARCHAR(255),
                bio TEXT,
                favorite_mushroom VARCHAR(255),
                role VARCHAR(50) DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                google_id VARCHAR(255) UNIQUE
            )
        ''')
        
        # Create journal_entries table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS journal_entries (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                date VARCHAR(10) NOT NULL,
                location VARCHAR(255),
                species_found VARCHAR(255),
                quantity VARCHAR(100),
                weather_conditions VARCHAR(255),
                temperature VARCHAR(50),
                humidity VARCHAR(50),
                entry_text TEXT,
                photo_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create forum_posts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS forum_posts (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                category VARCHAR(100),
                author VARCHAR(255),
                author_id INTEGER REFERENCES users(id),
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_auto_generated BOOLEAN DEFAULT FALSE,
                source VARCHAR(255)
            )
        ''')
        
        # Create admin user if it doesn't exist
        cursor.execute("SELECT * FROM users WHERE username = %s", ("admin",))
        if not cursor.fetchone():
            admin_password = pwd_context.hash("admin123")
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                ("admin", "admin@mushroomapp.com", admin_password, "admin")
            )
        
        conn.commit()
    except Exception as e:
        print(f"Database initialization error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# Helper functions
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = verify_token(token)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, username, email, role FROM users WHERE username = %s", (payload["sub"],))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        return User(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            role=user["role"]
        )
    finally:
        cursor.close()
        conn.close()

async def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Routes
@app.get("/")
async def read_root():
    return {"message": "Welcome to Forager's Friend API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@app.post("/auth/signup")
async def signup(user_create: UserCreate):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", 
                      (user_create.username, user_create.email))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username or email already registered")
        
        # Create user
        password_hash = pwd_context.hash(user_create.password)
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (user_create.username, user_create.email, password_hash)
        )
        user_id = cursor.fetchone()["id"]
        conn.commit()
        
        # Create token
        access_token = create_access_token(data={"sub": user_create.username})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "username": user_create.username,
                "email": user_create.email,
                "role": "user"
            }
        }
    finally:
        cursor.close()
        conn.close()

@app.post("/auth/login")
async def login(user_login: UserLogin):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM users WHERE username = %s", (user_login.username,))
        user = cursor.fetchone()
        
        if not user or not pwd_context.verify(user_login.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        access_token = create_access_token(data={"sub": user["username"]})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"]
            }
        }
    finally:
        cursor.close()
        conn.close()

@app.get("/user/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT * FROM users WHERE id = %s",
            (current_user.id,)
        )
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "full_name": user.get("full_name", ""),
            "location": user.get("location", ""),
            "bio": user.get("bio", ""),
            "favorite_mushroom": user.get("favorite_mushroom", ""),
            "role": user["role"],
            "created_at": user["created_at"]
        }
    finally:
        cursor.close()
        conn.close()

@app.put("/user/profile")
async def update_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        update_fields = []
        update_values = []
        
        if user_update.email:
            update_fields.append("email = %s")
            update_values.append(user_update.email)
        if user_update.full_name is not None:
            update_fields.append("full_name = %s")
            update_values.append(user_update.full_name)
        if user_update.location is not None:
            update_fields.append("location = %s")
            update_values.append(user_update.location)
        if user_update.bio is not None:
            update_fields.append("bio = %s")
            update_values.append(user_update.bio)
        if user_update.favorite_mushroom is not None:
            update_fields.append("favorite_mushroom = %s")
            update_values.append(user_update.favorite_mushroom)
        
        if update_fields:
            update_values.append(current_user.id)
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s"
            cursor.execute(query, update_values)
            conn.commit()
        
        return {"message": "Profile updated successfully"}
    finally:
        cursor.close()
        conn.close()

@app.post("/user/change-password")
async def change_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_user)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT password_hash FROM users WHERE id = %s", (current_user.id,))
        user = cursor.fetchone()
        
        if not pwd_context.verify(password_change.current_password, user["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        new_password_hash = pwd_context.hash(password_change.new_password)
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (new_password_hash, current_user.id)
        )
        conn.commit()
        
        return {"message": "Password changed successfully"}
    finally:
        cursor.close()
        conn.close()

@app.post("/journal/entries")
async def create_journal_entry(
    date: str = Form(...),
    location: str = Form(...),
    species_found: str = Form(""),
    quantity: str = Form(""),
    weather_conditions: str = Form(""),
    temperature: str = Form(""),
    humidity: str = Form(""),
    entry_text: str = Form(...),
    photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        photo_url = None
        if photo and photo.filename:
            # Here you would upload to a storage service
            # For now, we'll store a placeholder
            photo_url = f"/uploads/{photo.filename}"
        
        cursor.execute(
            """INSERT INTO journal_entries 
            (user_id, date, location, species_found, quantity, weather_conditions, 
             temperature, humidity, entry_text, photo_url) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (current_user.id, date, location, species_found, quantity, 
             weather_conditions, temperature, humidity, entry_text, photo_url)
        )
        entry_id = cursor.fetchone()["id"]
        conn.commit()
        
        return {"message": "Journal entry created successfully", "id": entry_id}
    finally:
        cursor.close()
        conn.close()

@app.get("/journal/entries")
async def get_journal_entries(current_user: User = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT * FROM journal_entries WHERE user_id = %s ORDER BY created_at DESC",
            (current_user.id,)
        )
        entries = cursor.fetchall()
        
        return [dict(entry) for entry in entries]
    finally:
        cursor.close()
        conn.close()

@app.delete("/journal/entries/{entry_id}")
async def delete_journal_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "DELETE FROM journal_entries WHERE id = %s AND user_id = %s",
            (entry_id, current_user.id)
        )
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Entry not found")
        
        conn.commit()
        return {"message": "Entry deleted successfully"}
    finally:
        cursor.close()
        conn.close()

@app.get("/journal/stats")
async def get_journal_stats(current_user: User = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Total entries
        cursor.execute(
            "SELECT COUNT(*) as count FROM journal_entries WHERE user_id = %s",
            (current_user.id,)
        )
        total_entries = cursor.fetchone()["count"]
        
        # Unique species
        cursor.execute(
            "SELECT COUNT(DISTINCT species_found) as count FROM journal_entries WHERE user_id = %s AND species_found != ''",
            (current_user.id,)
        )
        unique_species = cursor.fetchone()["count"]
        
        # Unique locations
        cursor.execute(
            "SELECT COUNT(DISTINCT location) as count FROM journal_entries WHERE user_id = %s",
            (current_user.id,)
        )
        unique_locations = cursor.fetchone()["count"]
        
        return {
            "total_entries": total_entries,
            "unique_species": unique_species,
            "unique_locations": unique_locations
        }
    finally:
        cursor.close()
        conn.close()

@app.post("/weather/check")
async def check_weather(weather_request: WeatherRequest):
    if not OPENWEATHER_API_KEY:
        raise HTTPException(status_code=500, detail="Weather API key not configured")
    
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": weather_request.lat,
            "lon": weather_request.lon,
            "appid": OPENWEATHER_API_KEY,
            "units": "metric"
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        temp = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        conditions = data["weather"][0]["main"].lower()
        rain = "rain" in conditions or "drizzle" in conditions
        
        is_good = (
            10 <= temp <= 25 and
            humidity >= 60 and
            not rain
        )
        
        recommendation = {
            "is_good_for_foraging": is_good,
            "temperature": temp,
            "humidity": humidity,
            "conditions": data["weather"][0]["main"],
            "description": data["weather"][0]["description"],
            "reasons": []
        }
        
        if temp < 10:
            recommendation["reasons"].append("Too cold - mushrooms grow slowly")
        elif temp > 25:
            recommendation["reasons"].append("Too hot - mushrooms may dry out")
        else:
            recommendation["reasons"].append("Good temperature for mushroom growth")
        
        if humidity < 60:
            recommendation["reasons"].append("Low humidity - mushrooms need moisture")
        else:
            recommendation["reasons"].append("Good humidity levels")
        
        if rain:
            recommendation["reasons"].append("Recent rain is good, but wait for it to stop")
        
        return recommendation
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Weather API error: {str(e)}")

# Admin routes
@app.get("/admin/check")
async def check_admin(admin_user: User = Depends(get_admin_user)):
    return {"is_admin": True, "username": admin_user.username}

@app.get("/admin/stats")
async def get_admin_stats(admin_user: User = Depends(get_admin_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        stats = {}
        
        # Total users
        cursor.execute("SELECT COUNT(*) as count FROM users")
        stats["total_users"] = cursor.fetchone()["count"]
        
        # Active users (with journal entries)
        cursor.execute("SELECT COUNT(DISTINCT user_id) as count FROM journal_entries")
        stats["active_users"] = cursor.fetchone()["count"]
        
        # Total journal entries
        cursor.execute("SELECT COUNT(*) as count FROM journal_entries")
        stats["total_entries"] = cursor.fetchone()["count"]
        
        # Unique species found
        cursor.execute("SELECT COUNT(DISTINCT species_found) as count FROM journal_entries WHERE species_found != ''")
        stats["total_species"] = cursor.fetchone()["count"]
        
        # Total locations
        cursor.execute("SELECT COUNT(DISTINCT location) as count FROM journal_entries")
        stats["total_locations"] = cursor.fetchone()["count"]
        
        # Admin count
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'admin'")
        stats["admin_count"] = cursor.fetchone()["count"]
        
        # New users today
        cursor.execute(
            "SELECT COUNT(*) as count FROM users WHERE DATE(created_at) = DATE('now')"
        )
        stats["new_users_today"] = cursor.fetchone()["count"]
        
        return stats
    finally:
        cursor.close()
        conn.close()

@app.get("/admin/users")
async def get_all_users(admin_user: User = Depends(get_admin_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT u.*, COUNT(j.id) as journal_count 
            FROM users u 
            LEFT JOIN journal_entries j ON u.id = j.user_id 
            GROUP BY u.id, u.username, u.email, u.role, u.created_at
            ORDER BY u.created_at DESC
        """)
        users = cursor.fetchall()
        
        return [dict(user) for user in users]
    finally:
        cursor.close()
        conn.close()

@app.get("/admin/journal-entries")
async def get_all_journal_entries(
    user_id: Optional[int] = None,
    admin_user: User = Depends(get_admin_user)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if user_id:
            cursor.execute("""
                SELECT j.*, u.username 
                FROM journal_entries j 
                JOIN users u ON j.user_id = u.id 
                WHERE j.user_id = %s 
                ORDER BY j.created_at DESC
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT j.*, u.username 
                FROM journal_entries j 
                JOIN users u ON j.user_id = u.id 
                ORDER BY j.created_at DESC
            """)
        
        entries = cursor.fetchall()
        return [dict(entry) for entry in entries]
    finally:
        cursor.close()
        conn.close()

@app.delete("/admin/journal-entries/{entry_id}")
async def admin_delete_entry(
    entry_id: int,
    admin_user: User = Depends(get_admin_user)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM journal_entries WHERE id = %s", (entry_id,))
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Entry not found")
        
        conn.commit()
        return {"message": "Entry deleted successfully"}
    finally:
        cursor.close()
        conn.close()

@app.get("/admin/analytics")
async def get_admin_analytics(admin_user: User = Depends(get_admin_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Most active users
        cursor.execute("""
            SELECT u.username, COUNT(j.id) as entry_count 
            FROM users u 
            JOIN journal_entries j ON u.id = j.user_id 
            GROUP BY u.username 
            ORDER BY entry_count DESC 
            LIMIT 5
        """)
        most_active = [dict(row) for row in cursor.fetchall()]
        
        # Popular species
        cursor.execute("""
            SELECT species_found, COUNT(*) as count 
            FROM journal_entries 
            WHERE species_found != '' 
            GROUP BY species_found 
            ORDER BY count DESC 
            LIMIT 5
        """)
        popular_species = [dict(row) for row in cursor.fetchall()]
        
        # Top locations
        cursor.execute("""
            SELECT location, COUNT(*) as count 
            FROM journal_entries 
            GROUP BY location 
            ORDER BY count DESC 
            LIMIT 5
        """)
        top_locations = [dict(row) for row in cursor.fetchall()]
        
        # Recent activity
        cursor.execute("""
            SELECT j.*, u.username 
            FROM journal_entries j 
            JOIN users u ON j.user_id = u.id 
            ORDER BY j.created_at DESC 
            LIMIT 10
        """)
        recent_activity = [dict(row) for row in cursor.fetchall()]
        
        return {
            "most_active_users": most_active,
            "popular_species": popular_species,
            "top_locations": top_locations,
            "recent_activity": recent_activity
        }
    finally:
        cursor.close()
        conn.close()

# Forum/News routes (simplified without external dependencies)
@app.post("/forum/posts")
async def create_forum_post(
    post: ForumPost,
    current_user: User = Depends(get_current_user)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """INSERT INTO forum_posts 
            (title, content, category, author, author_id, image_url) 
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (post.title, post.content, post.category, 
             current_user.username, current_user.id, post.image_url)
        )
        post_id = cursor.fetchone()["id"]
        conn.commit()
        
        return {"message": "Forum post created", "id": post_id}
    finally:
        cursor.close()
        conn.close()

@app.get("/forum/posts")
async def get_forum_posts(
    category: Optional[str] = None,
    is_auto: Optional[bool] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = "SELECT * FROM forum_posts WHERE 1=1"
        params = []
        
        if category:
            query += " AND category = %s"
            params.append(category)
        
        if is_auto is not None:
            query += " AND is_auto_generated = %s"
            params.append(is_auto)
        
        query += " ORDER BY created_at DESC LIMIT 50"
        
        cursor.execute(query, params)
        posts = cursor.fetchall()
        
        return [dict(post) for post in posts]
    finally:
        cursor.close()
        conn.close()

@app.post("/admin/news/fetch-now")
async def fetch_news_now(admin_user: User = Depends(get_admin_user)):
    # Simple Reddit API call without external dependencies
    try:
        headers = {"User-Agent": "ForagersFriend/1.0"}
        
        # Fetch from r/mycology
        response = requests.get(
            "https://www.reddit.com/r/mycology/top.json?limit=5&t=week",
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            posts_created = 0
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                for post in data["data"]["children"]:
                    post_data = post["data"]
                    
                    # Simple mushroom relevance check
                    title = post_data["title"].lower()
                    if any(word in title for word in ["mushroom", "fungi", "mycology", "foraging"]):
                        cursor.execute(
                            """INSERT INTO forum_posts 
                            (title, content, category, author, is_auto_generated, source) 
                            VALUES (%s, %s, %s, %s, %s, %s)""",
                            (post_data["title"], 
                             post_data.get("selftext", "")[:500],
                             "news",
                             "NewsBot",
                             True,
                             "Reddit r/mycology")
                        )
                        posts_created += 1
                
                conn.commit()
                return {"message": f"Created {posts_created} news posts"}
            finally:
                cursor.close()
                conn.close()
        else:
            return {"message": "Failed to fetch news", "status": response.status_code}
            
    except Exception as e:
        return {"message": f"Error fetching news: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
