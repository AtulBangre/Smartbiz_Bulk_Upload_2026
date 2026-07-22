import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

import certifi

load_dotenv()

async def test_connection():
    uri = os.getenv("MONGODB_URI")
    print("Testing MongoDB connection...")
    
    try:
        client = AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
        # Send a ping to confirm a successful connection
        await client.admin.command('ping')
        print("✅ Ping successful! You successfully connected to MongoDB!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_connection())
