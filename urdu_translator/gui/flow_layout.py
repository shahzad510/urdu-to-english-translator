"""A row of controls that wraps onto another line when the width is tight."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    """Place widgets left to right, then on a new row when the line is full."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        """Preferred size keeps items on one row when the parent is wide enough."""
        width = self.spacing() * max(0, len(self._items) - 1)
        height = 0
        for item in self._items:
            hint = item.sizeHint()
            width += hint.width()
            height = max(height, hint.height())
        margins = self.contentsMargins()
        return QSize(
            width + margins.left() + margins.right(),
            max(height, 0) + margins.top() + margins.bottom(),
        )

    def minimumSize(self) -> QSize:
        """Minimum width is the widest child so the parent can shrink and wrap.

        A previous single-row width sum was treated as the window minimum on
        Windows font metrics and pushed minimumWidth above 960px.
        """
        size = QSize()
        for item in self._items:
            hint = item.sizeHint()
            minimum = item.minimumSize()
            size = size.expandedTo(
                QSize(max(hint.width(), minimum.width()), max(hint.height(), minimum.height()))
            )
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _arrange(self, rect: QRect, *, apply: bool) -> int:
        margins = self.contentsMargins()
        available = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        gap = self.spacing()
        x = available.x()
        y = available.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + gap
            if line_height and next_x - gap > available.right() + 1:
                x = available.x()
                y += line_height + gap
                next_x = x + hint.width() + gap
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()
