import importlib.metadata


def get_version():
    try:
        return importlib.metadata.version("yal-cmd")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
