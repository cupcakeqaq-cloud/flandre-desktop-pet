import os

if os.name == "nt":
    _orig_mkdir = os.mkdir

    def _mkdir(path, mode=0o777):
        return _orig_mkdir(path, 0o777)

    os.mkdir = _mkdir
