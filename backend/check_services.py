"""Read-only deployment checks. Never prints credentials or application data."""
import asyncio
import os
from pathlib import Path

import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))


async def main():
    failed = False
    try:
        conn = await asyncpg.connect(os.environ['DATABASE_URL'], timeout=15,
                                     statement_cache_size=0)
        try:
            for table, column in [('messages', 'sources'), ('room_messages', 'sources'),
                                  ('documents', 'status'), ('document_chunks', 'embedding'),
                                  ('room_members', 'role'), ('user_memories', 'content')]:
                exists = await conn.fetchval(
                    'select exists(select 1 from information_schema.columns '
                    'where table_schema=$1 and table_name=$2 and column_name=$3)',
                    'public', table, column)
                if not exists:
                    raise RuntimeError('Required database migration is missing')
            print('Database: connected; required schema columns present')
        finally:
            await conn.close()
    except Exception as exc:
        print(f'Database: FAILED ({type(exc).__name__})')
        failed = True

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.get(os.environ['SUPABASE_URL'].rstrip('/') + '/auth/v1/settings',
                                        headers={'apikey': os.environ['SUPABASE_ANON_KEY']})
            response.raise_for_status()
            print('Supabase Auth: reachable; public key accepted')
        except Exception as exc:
            print(f'Supabase Auth: FAILED ({type(exc).__name__})')
            failed = True
        try:
            response = await client.get('https://api.groq.com/openai/v1/models',
                                        headers={'Authorization': 'Bearer ' + os.environ['GROQ_API_KEY']})
            response.raise_for_status()
            from app.llm import main_model, fast_model
            available = {model['id'] for model in response.json()['data']}
            for setting, model in [('GROQ_MODEL', main_model()), ('GROQ_FAST_MODEL', fast_model())]:
                if model not in available:
                    print(f'Groq: {setting} model unavailable: {model}')
                    raise RuntimeError('Configured model is unavailable')
            print('Groq: credentials accepted; both configured models listed')
        except Exception as exc:
            print(f'Groq: FAILED ({type(exc).__name__})')
            failed = True
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
