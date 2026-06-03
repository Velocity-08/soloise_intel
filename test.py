from supabase import create_client

SUPABASE_URL = "https://yriwptbsnqmalmbqnbgn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlyaXdwdGJzbnFtYWxtYnFuYmduIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTkxMTcwMiwiZXhwIjoyMDk1NDg3NzAyfQ.ukoBlzV-78BmyGHLwZGAkA5Vcg4KHe4c0GnQ3Dgh1uc"

print("Testing Supabase connection...")
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Client created")
    
    # Try to query a table
    result = supabase.table("api_keys").select("*").limit(1).execute()
    print(f"✅ Query successful! Found {len(result.data)} keys")
    print(f"First key: {result.data[0]['key_prefix'] if result.data else 'None'}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print(f"Error type: {type(e).__name__}")