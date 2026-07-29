APP_STYLE = """
QWidget {
    color: #EEF2FF;
    font-family: "Segoe UI";
    font-size: 14px;
}
QMainWindow, QDialog {
    background: #0B1020;
}
QFrame#card {
    background: #141B2D;
    border: 1px solid #25304A;
    border-radius: 16px;
}
QLabel#muted {
    color: #8994AE;
}
QLabel#title {
    font-size: 27px;
    font-weight: 700;
}
QLabel#section {
    font-size: 18px;
    font-weight: 650;
}
QPushButton {
    background: #635BFF;
    border: none;
    border-radius: 10px;
    padding: 10px 18px;
    font-weight: 600;
}
QPushButton:hover {
    background: #746DFF;
}
QPushButton:pressed {
    background: #5148E5;
}
QPushButton#secondary {
    background: #202A42;
}
QPushButton#danger {
    background: #3A1F2A;
    color: #FF9BB3;
}
QComboBox, QLineEdit, QKeySequenceEdit {
    background: #0E1527;
    border: 1px solid #2B3650;
    border-radius: 9px;
    padding: 8px 10px;
    min-height: 22px;
}
QTableWidget {
    background: #10172A;
    alternate-background-color: #131C31;
    border: 1px solid #25304A;
    border-radius: 12px;
    gridline-color: #202B43;
    selection-background-color: #313B74;
}
QHeaderView::section {
    background: #171F34;
    border: none;
    padding: 8px;
    color: #9DA8C2;
}
QMenu {
    background: #FFFFFF;
    color: #182033;
    border: 1px solid #C8CFDC;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item {
    background: transparent;
    color: #182033;
    border-radius: 5px;
    padding: 7px 28px 7px 12px;
}
QMenu::item:selected {
    background: #E7EAFE;
    color: #182033;
}
QMenu::item:disabled {
    color: #7A8499;
}
QMenu::separator {
    height: 1px;
    background: #DCE1EB;
    margin: 5px 8px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: #34405E;
    border-radius: 5px;
    min-height: 30px;
}
"""
