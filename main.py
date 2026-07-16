from app.core.app import JarvisApp
from app.core.kernel import JarvisKernel


def main():
    kernel = JarvisKernel()
    kernel.boot()

    app = JarvisApp(kernel.registry)
    app.run()


if __name__ == "__main__":
    main()