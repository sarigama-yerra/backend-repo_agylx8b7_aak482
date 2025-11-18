import os
import hashlib
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from database import db, create_document, get_documents
from schemas import User as UserSchema, Post as PostSchema, ContactMessage as ContactSchema

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Utility functions
# -----------------------------

def hash_password(password: str, salt: Optional[str] = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt.encode('utf-8'), 100_000
    ).hex()
    return f"{salt}${pwd_hash}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt, pwd_hash = stored.split('$')
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100_000).hex()
    return secrets.compare_digest(test, pwd_hash)

# -----------------------------
# Models
# -----------------------------

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    token: str
    name: str
    email: EmailStr

class BlogPostOut(BaseModel):
    title: str
    slug: str
    excerpt: str
    cover_image: Optional[str] = None
    tags: List[str] = []
    created_at: Optional[datetime] = None

class ContactIn(BaseModel):
    name: str
    email: EmailStr
    message: str

# -----------------------------
# Base routes
# -----------------------------

@app.get("/")
def read_root():
    return {"message": "FastAPI backend running"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# -----------------------------
# Auth endpoints (simple token auth)
# -----------------------------

@app.post("/api/auth/register", response_model=AuthResponse)
def register(payload: RegisterRequest):
    # Check if user exists
    existing = db["user"].find_one({"email": payload.email}) if db else None
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    password_hash = hash_password(payload.password)
    doc = UserSchema(name=payload.name, email=payload.email, password_hash=password_hash)
    user_id = create_document("user", doc)

    token = secrets.token_urlsafe(32)
    db["user"].update_one({"_id": db["user"].find_one({"_id": db["user"].find_one({"email": payload.email})["_id"]})["_id"]}, {"$push": {"session_tokens": token}})
    return AuthResponse(token=token, name=payload.name, email=payload.email)

@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    user = db["user"].find_one({"email": payload.email}) if db else None
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_urlsafe(32)
    db["user"].update_one({"_id": user["_id"]}, {"$push": {"session_tokens": token}})
    return AuthResponse(token=token, name=user.get("name", ""), email=user.get("email", ""))

# -----------------------------
# Pricing (static)
# -----------------------------

@app.get("/api/pricing")
def pricing():
    return {
        "plans": [
            {
                "name": "Starter",
                "price": 0,
                "period": "mo",
                "features": ["Up to 3 projects", "Basic analytics", "Community support"],
                "cta": "Get started"
            },
            {
                "name": "Growth",
                "price": 19,
                "period": "mo",
                "features": ["Unlimited projects", "Advanced analytics", "Email support"],
                "cta": "Start free trial",
                "highlight": True
            },
            {
                "name": "Scale",
                "price": 49,
                "period": "mo",
                "features": ["Priority support", "SSO & Roles", "Custom integrations"],
                "cta": "Contact sales"
            }
        ]
    }

# -----------------------------
# Blog endpoints
# -----------------------------

@app.get("/api/blog", response_model=List[BlogPostOut])
def list_posts():
    posts = get_documents("post", {}, limit=20)
    out = []
    for p in posts:
        out.append(BlogPostOut(
            title=p.get("title"),
            slug=p.get("slug"),
            excerpt=p.get("excerpt"),
            cover_image=p.get("cover_image"),
            tags=p.get("tags", []),
            created_at=p.get("created_at")
        ))
    return out

@app.get("/api/blog/{slug}")
def get_post(slug: str):
    post = db["post"].find_one({"slug": slug}) if db else None
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return {
        "title": post.get("title"),
        "slug": post.get("slug"),
        "excerpt": post.get("excerpt"),
        "content": post.get("content"),
        "cover_image": post.get("cover_image"),
        "tags": post.get("tags", []),
        "created_at": post.get("created_at"),
    }

# -----------------------------
# Contact form
# -----------------------------

@app.post("/api/contact")
def submit_contact(payload: ContactIn):
    doc = ContactSchema(name=payload.name, email=payload.email, message=payload.message)
    _id = create_document("contactmessage", doc)
    return {"ok": True, "id": _id}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
