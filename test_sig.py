import asyncio
import ai_service
import inspect

async def main():
    sig = inspect.signature(ai_service.generate_section)
    print(f"Signature: {sig}")
    try:
        # We don't actually want to call it because it makes AI requests
        # but we can check if it accepts the argument
        bound = sig.bind("base", "01.01.2000", "12:00", "Moscow", return_json=True)
        print("Binding success")
    except TypeError as e:
        print(f"TypeError: {e}")

asyncio.run(main())
