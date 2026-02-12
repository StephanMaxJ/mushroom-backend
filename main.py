# Updated main.py with CORS configuration

# Other imports...
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://mushroom-backend-frwl.onrender.com",
        # other origins...
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Other configurations...
