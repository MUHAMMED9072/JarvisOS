from app.core.kernel import JarvisKernel

kernel = JarvisKernel()

kernel.boot()

print()

print("Running:", kernel.running)

print()

print("Registered Services:")

for service in kernel.registry.list_services():
    print("-", service)

print()

print("Loaded Skills:")

for skill in kernel.skill_manager.all_skills():
    print("-", skill.name, "->", skill.intent)