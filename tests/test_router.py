from app.core.router import CommandRouter

router = CommandRouter()

commands = [
    "Open Chrome",
    "Shutdown computer",
    "Continue the Jarvis project",
    "Build the plugin",
    "Who is Elon Musk?",
    "How are you?",
]

for cmd in commands:
    result = router.route(cmd)

    print(f"{cmd}")

    print(result.command_type)

    print("-" * 40)