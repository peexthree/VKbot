import asyncio
import os
import aiohttp
from database.config import URL, KEY, HEADERS

async def main():
    async with aiohttp.ClientSession() as session:
        with open("database/hidden_promos_migration.sql", "r", encoding="utf-8") as f:
            sql = f.read()

        print("Applying migration via exec_sql...")
        url = f"{URL}/rest/v1/rpc/exec_sql"
        async with session.post(url, headers=HEADERS, json={"sql_query": sql}) as r:
            print(f"Status: {r.status}")
            text = await r.text()
            print(f"Response: {text}")

if __name__ == "__main__":
    asyncio.run(main())
