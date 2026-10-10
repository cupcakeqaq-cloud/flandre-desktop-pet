import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase

from config import FONT_DIR
from data_manager import ensure_dirs
from pet_window import PetWindow
from tray import Tray

READABLE_FONT = "NotoSansSC-VF.ttf"


def setup_font(app):
    """界面字体。

    默认用随程序打包的思源黑体（Noto Sans SC，可变字体，取 DemiBold 600 字重）；
    设置里勾了「使用系统字体」就回落微软雅黑。
    """
    from data_manager import load_settings
    if load_settings().get("ui_font", "source") == "system":
        app.setFont(QFont("Microsoft YaHei", 9))
        return
    fp = FONT_DIR / READABLE_FONT
    if fp.exists():
        fid = QFontDatabase.addApplicationFont(str(fp))
        if fid >= 0:
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                f = QFont(families[0], 10)
                f.setWeight(QFont.Weight.DemiBold)
                app.setFont(f)
                return
    app.setFont(QFont("Microsoft YaHei", 9))


def main():
    # 高分屏：保留真实缩放比例，配合高分辨率贴图避免模糊
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("芙兰朵露")
    app.setQuitOnLastWindowClosed(False)
    setup_font(app)

    ensure_dirs()

    pet = PetWindow()
    pet.show()

    tray = Tray(app, pet)
    pet.set_tray(tray)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
