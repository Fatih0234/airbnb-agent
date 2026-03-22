import asyncio

from app.agent import create_agent


async def main():
    print("Airbnb Stay-Matching Copilot")
    print("Type 'quit' or Ctrl+C to exit.\n")

    agent = create_agent()
    message_history = []

    async with agent:
        while True:
            try:
                user_input = await asyncio.to_thread(input, "You: ")
            except (KeyboardInterrupt, EOFError):
                print("\nBye!")
                break

            user_input = user_input.strip()
            if not user_input or user_input.lower() in ("quit", "exit"):
                print("Bye!")
                break

            result = await agent.run(user_input, message_history=message_history)
            message_history = result.all_messages()

            print(f"\nAgent: {result.output}\n")


if __name__ == "__main__":
    asyncio.run(main())
