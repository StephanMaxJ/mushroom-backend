from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS settings
origins = [
    "https://mushroom-backend-frwl.onrender.com",
    # Add other allowed origins here.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define your routes, models, and database functions here
@app.get("/")
def read_root():
    return {"Hello": "World"}

# Add other routes, models, and database functions as needed
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)