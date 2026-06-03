import hashlib
from supabase import create_client

SUPABASE_URL = "https://yriwptbsnqmalmbqnbgn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlyaXdwdGJzbnFtYWxtYnFuYmduIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTkxMTcwMiwiZXhwIjoyMDk1NDg3NzAyfQ.ukoBlzV-78BmyGHLwZGAkA5Vcg4KHe4c0GnQ3Dgh1uc"

# The key from your frontend
raw_key = "sk-sol-6ea8d0f4730b2bf53d7ed735dbdfee9b8c9b218b"
calculated_hash = hashlib.sha256(raw_key.encode()).hexdigest()

print(f"Raw key: {raw_key}")
print(f"Calculated hash: {calculated_hash}")
print(f"Expected prefix: {raw_key[:16]}")

# Get the actual hash from database
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
result = supabase.table("api_keys").select("key_hash, key_prefix").eq("key_prefix", "sk-sol-6ea8d0f47").execute()

if result.data:
    db_hash = result.data[0]["key_hash"]
    db_prefix = result.data[0]["key_prefix"]
    print(f"\nDatabase hash: {db_hash}")
    print(f"Database prefix: {db_prefix}")
    print(f"\nHashes match: {calculated_hash == db_hash}")
else:
    print("Key not found in database")