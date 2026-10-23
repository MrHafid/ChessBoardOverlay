import sys

from overlay_app import OverlayApp


def enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()


def main() -> None:
    enable_windows_dpi_awareness()
    OverlayApp().run()


if __name__ == "__main__":
    main()
