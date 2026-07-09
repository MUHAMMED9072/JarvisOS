from app.events import event_bus


def on_message(text: str):
    print(f"Received: {text}")


event_bus.subscribe("chat.message", on_message)

event_bus.publish("chat.message", "Hello Jarvis")
