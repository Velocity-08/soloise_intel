"""
Key Generator
"""

import os
import secrets
import hashlib
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def generate_api_key() -> str:
    random_part = secrets.token_hex(20)
    return f"sk-sol-{random_part}"

def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()

def create_api_key(user_id: str, name: str = "My Key") -> dict:
    raw_key = generate_api_key()
    key_hash = hash_key(raw_key)
    key_prefix = raw_key[:16]

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )

    response = supabase.table("api_keys").insert({
        "user_id": user_id,
        "name": name,
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "is_active": True,
    }).execute()

    key_id = response.data[0]["id"]

    return {
        "raw_key": raw_key,
        "key_prefix": key_prefix,
        "key_id": key_id,
        "name": name,
    }

if __name__ == "__main__":
    result = create_api_key(
        user_id="593f97ce-6532-4609-a92b-01a0f07cde79",
        name="Test Key",
    )
    print("\nYour key (copy it now — shown only once):")
    print(f"{result['raw_key']}\n")
