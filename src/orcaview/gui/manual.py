"""Search a local index and open corresponding official HTML or PDF sections."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from orcaview.i18n import tr
from orcaview.core.manual import lookup, WEB_ROOT, PDF_URL


class ManualDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ORCA 6.1.1 manual"))
        self.resize(740, 480)
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("Search sections, methods or keywords, e.g. 3.18, EOM or MaxIter"))
        layout.addWidget(self.query)
        self.results = QTreeWidget()
        self.results.setHeaderLabels((tr("Section"), tr("Manual heading"), tr("PDF page")))
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.header().setStretchLastSection(False)
        self.results.header().setSectionResizeMode(1, self.results.header().ResizeMode.Stretch)
        layout.addWidget(self.results)
        self.count = QLabel()
        buttons = QHBoxLayout()
        buttons.addWidget(self.count)
        buttons.addStretch()
        self.web = QPushButton(tr("Open web version"))
        self.pdf = QPushButton(tr("Open PDF page"))
        for button, pdf in ((self.web, False), (self.pdf, True)):
            button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False, pdf=pdf: self.open_section(pdf))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.results.itemDoubleClicked.connect(lambda *_: self.open_section(False))
        self.query.textChanged.connect(self.refresh)
        self.refresh("")

    def refresh(self, text):
        rows = lookup(text)
        self.results.clear()
        for number, title, path, page, _ in rows:
            item = QTreeWidgetItem(self.results, (number, title, page))
            item.setData(0, Qt.ItemDataRole.UserRole, path)
        if rows:
            self.results.setCurrentItem(self.results.topLevelItem(0))
        self.count.setText(tr("{count} sections", count=len(rows)))
        self.web.setEnabled(bool(rows))
        self.pdf.setEnabled(bool(rows))

    def open_section(self, pdf):
        row = self.results.currentItem()
        if row is not None:
            url = PDF_URL + "#page=" + row.text(2) if pdf else WEB_ROOT + row.data(0, Qt.ItemDataRole.UserRole)
            QDesktopServices.openUrl(QUrl(url))
