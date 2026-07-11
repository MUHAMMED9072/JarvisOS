from app.cortex.input_manager import InputManager

manager = InputManager()

request = manager.receive(
    "Hello Jarvis",
    source="voice",
)

print(request)