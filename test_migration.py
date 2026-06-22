import asyncio
from database.core import init_db, close_db, call_rpc

async def main():
    await init_db()
    # Проверяем наличие таблицы
    res = await call_rpc("exec_sql", {"sql_query": "SELECT count(*) FROM hidden_promos"})
    print(f"Table hidden_promos exists: {res}")

    # Проверяем наличие функции
    res = await call_rpc("exec_sql", {"sql_query": "SELECT proname FROM pg_proc WHERE proname = 'activate_hidden_promo'"})
    print(f"Function activate_hidden_promo exists: {res}")

    await close_db()

if __name__ == "__main__":
    asyncio.run(main())
