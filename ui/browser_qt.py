"""Navegador Chromium opcional executado fora do processo Tkinter.

Este módulo só é usado pelo subprocesso iniciado por ``ui.browser``. O perfil
WebEngine é anônimo/em memória: não há histórico, cookies persistentes ou
cache persistente gravados pelo navegador do aplicativo.
"""

from __future__ import annotations

import json
import sys
import threading

from .browser import ABOUT_BLANK, BrowserInputError, normalize_browser_url

try:  # PyQt6-WebEngine é uma dependência opcional.
    from PyQt6.QtCore import QCoreApplication, QEvent, QObject, Qt, QUrl, pyqtSignal
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLineEdit,
        QMainWindow,
        QStatusBar,
        QTabWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

    QT_WEBENGINE_AVAILABLE = True
except ImportError:  # Mantém a importação segura quando o extra não existe.
    QT_WEBENGINE_AVAILABLE = False


MISSING_ENGINE_MESSAGE = (
    "O motor Chromium não está instalado. Execute: "
    "python -m pip install -r requirements-optional.txt"
)


def _url_is_allowed(url: QUrl) -> bool:
    """Valida uma QUrl sem expor o endereço em logs ou mensagens."""

    text = url.toString()
    if text.lower() == ABOUT_BLANK:
        return True
    if url.scheme().lower() not in {"http", "https"} or not url.host():
        return False
    try:
        normalize_browser_url(text, allow_about_blank=False)
    except BrowserInputError:
        return False
    return True


if QT_WEBENGINE_AVAILABLE:

    class _InitialCommandBridge(QObject):
        command_received = pyqtSignal(str)


    class BrowserPage(QWebEnginePage):
        """Página que permite apenas about:blank e navegação HTTP(S)."""

        navigation_blocked = pyqtSignal()
        render_error = pyqtSignal()

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            if not _url_is_allowed(url):
                if is_main_frame:
                    self.navigation_blocked.emit()
                return False
            return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

        def createWindow(self, _window_type):
            browser = self.parent()
            while browser is not None and not isinstance(browser, BrowserWindow):
                browser = browser.parent()
            if browser is None:
                return None
            view = browser.add_tab(ABOUT_BLANK, switch=True)
            return view.page()


    class BrowserWindow(QMainWindow):
        """Janela moderna, sem marca de terceiros, com abas Chromium reais."""

        def __init__(self):
            super().__init__()
            self.setWindowTitle("Navegador")
            self.resize(1120, 760)
            self.setMinimumSize(720, 480)
            self.setStyleSheet(
                """
                QMainWindow, QWidget { background: #111827; color: #f9fafb; }
                QToolButton, QPushButton {
                    background: #1f2937; color: #e5e7eb; border: 0;
                    border-radius: 7px; padding: 7px 11px;
                }
                QToolButton:hover, QPushButton:hover { background: #374151; }
                QToolButton:pressed, QPushButton:pressed { background: #4b5563; }
                QLineEdit {
                    background: #1f2937; color: #f9fafb;
                    border: 1px solid #374151; border-radius: 9px;
                    padding: 8px 12px; selection-background-color: #7c3aed;
                }
                QTabWidget::pane { border: 0; background: #0b1220; }
                QTabBar::tab {
                    background: #1f2937; color: #9ca3af; padding: 9px 16px;
                    margin-right: 2px; border-top-left-radius: 7px;
                    border-top-right-radius: 7px;
                }
                QTabBar::tab:selected { background: #374151; color: #f9fafb; }
                QStatusBar { color: #9ca3af; background: #111827; }
                """
            )

            self._pages = []
            self.profile = QWebEngineProfile(parent=self)
            self.profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
            self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)

            root = QWidget(self)
            self.setCentralWidget(root)
            layout = QVBoxLayout(root)
            layout.setContentsMargins(10, 10, 10, 0)
            layout.setSpacing(8)

            toolbar = QHBoxLayout()
            toolbar.setSpacing(5)
            self.back_button = self._make_button("←", "Voltar", self.go_back)
            self.forward_button = self._make_button("→", "Avançar", self.go_forward)
            self.reload_button = self._make_button("↻", "Recarregar", self.reload)
            self.home_button = self._make_button("⌂", "Início", self.go_home)
            for button in (
                self.back_button,
                self.forward_button,
                self.reload_button,
                self.home_button,
            ):
                toolbar.addWidget(button)

            self.address_bar = QLineEdit()
            self.address_bar.setPlaceholderText("Digite um endereço http:// ou https://")
            self.address_bar.setClearButtonEnabled(True)
            self.address_bar.returnPressed.connect(self.navigate_from_address)
            toolbar.addWidget(self.address_bar, stretch=1)

            self.go_button = self._make_button("Ir", "Navegar", self.navigate_from_address)
            toolbar.addWidget(self.go_button)
            layout.addLayout(toolbar)

            self.tabs = QTabWidget()
            self.tabs.setDocumentMode(True)
            self.tabs.setTabsClosable(True)
            self.tabs.setMovable(True)
            self.tabs.tabCloseRequested.connect(self.close_tab)
            self.tabs.currentChanged.connect(self._current_tab_changed)
            self.new_tab_button = QToolButton()
            self.new_tab_button.setText("+")
            self.new_tab_button.setToolTip("Nova guia")
            self.new_tab_button.clicked.connect(lambda: self.add_tab(ABOUT_BLANK, switch=True))
            self.tabs.setCornerWidget(self.new_tab_button, Qt.Corner.TopRightCorner)
            layout.addWidget(self.tabs, stretch=1)

            self.setStatusBar(QStatusBar(self))
            self.add_tab(ABOUT_BLANK, switch=True)
            self._set_status("Pronto")

        @staticmethod
        def _make_button(text, tooltip, callback):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.clicked.connect(callback)
            return button

        def _set_status(self, text: str) -> None:
            # Mensagens deliberadamente genéricas: URLs não são escritas em
            # disco nem repetidas em status/saída do processo.
            self.statusBar().showMessage(text)

        def add_tab(self, url: str = ABOUT_BLANK, *, switch: bool = True):
            view = QWebEngineView()
            page = BrowserPage(self.profile, self)
            self._pages.append(page)
            view.setPage(page)
            index = self.tabs.addTab(view, "Nova guia")
            page.navigation_blocked.connect(self._navigation_blocked)
            page.renderProcessTerminated.connect(self._render_process_terminated)
            view.urlChanged.connect(lambda changed_url, v=view: self._url_changed(v, changed_url))
            view.titleChanged.connect(lambda title, v=view: self._title_changed(title, v))
            view.loadStarted.connect(lambda v=view: self._load_started(v))
            view.loadFinished.connect(lambda ok, v=view: self._load_finished(v, ok))
            view.loadProgress.connect(lambda progress, v=view: self._load_progress(v, progress))
            self.tabs.setTabToolTip(index, "Nova guia")
            if switch:
                self.tabs.setCurrentIndex(index)
            self._update_navigation_buttons()
            if url != ABOUT_BLANK:
                self._set_url(view, url)
            return view

        def _set_url(self, view, url: str) -> None:
            try:
                normalized = normalize_browser_url(url, allow_about_blank=True)
            except BrowserInputError:
                self._set_status("Endereço inválido: use apenas http:// ou https://.")
                return
            view.setUrl(QUrl(normalized))

        def current_view(self):
            view = self.tabs.currentWidget()
            return view if isinstance(view, QWebEngineView) else None

        def navigate_from_address(self) -> None:
            view = self.current_view()
            if view is None:
                return
            try:
                url = normalize_browser_url(self.address_bar.text(), allow_about_blank=True)
            except BrowserInputError:
                self._set_status("Endereço inválido: use apenas http:// ou https://.")
                return
            self._set_url(view, url)

        def go_back(self) -> None:
            view = self.current_view()
            if view is not None:
                view.back()

        def go_forward(self) -> None:
            view = self.current_view()
            if view is not None:
                view.forward()

        def reload(self) -> None:
            view = self.current_view()
            if view is not None:
                view.reload()

        def go_home(self) -> None:
            view = self.current_view()
            if view is not None:
                self._set_url(view, ABOUT_BLANK)

        def close_tab(self, index: int) -> None:
            widget = self.tabs.widget(index)
            if widget is None:
                return
            page = widget.page()
            self.tabs.removeTab(index)
            widget.deleteLater()
            if page in self._pages:
                self._pages.remove(page)
                page.deleteLater()
            if self.tabs.count() == 0:
                self.add_tab(ABOUT_BLANK, switch=True)
            self._update_navigation_buttons()

        def _current_tab_changed(self, _index: int) -> None:
            view = self.current_view()
            if view is None:
                self.address_bar.clear()
            else:
                self.address_bar.setText(view.url().toString())
            self._update_navigation_buttons()

        def _url_changed(self, view, url) -> None:
            index = self.tabs.indexOf(view)
            if index >= 0:
                self.tabs.setTabToolTip(index, "Navegação no navegador")
            if view is self.current_view():
                self.address_bar.setText(url.toString())
            self._update_navigation_buttons()

        def _title_changed(self, title: str, view) -> None:
            index = self.tabs.indexOf(view)
            if index < 0:
                return
            safe_title = title.strip() or "Nova guia"
            self.tabs.setTabText(index, safe_title[:80])

        def _load_started(self, view) -> None:
            if view is self.current_view():
                self._set_status("Carregando…")

        def _load_progress(self, view, progress: int) -> None:
            if view is self.current_view() and progress < 100:
                self._set_status(f"Carregando… {progress}%")

        def _load_finished(self, view, ok: bool) -> None:
            if view is not self.current_view():
                return
            if ok:
                self._set_status("Pronto")
            else:
                self._set_status(
                    "Não foi possível carregar a página. "
                    "Verifique o endereço ou a conexão."
                )
            self._update_navigation_buttons()

        def _navigation_blocked(self) -> None:
            self._set_status("Navegação bloqueada: somente http:// e https:// são permitidos.")

        def _render_process_terminated(self, *_args) -> None:
            self._set_status("O processo Chromium foi encerrado inesperadamente.")

        def _update_navigation_buttons(self) -> None:
            view = self.current_view()
            enabled = view is not None
            self.back_button.setEnabled(enabled and view.history().canGoBack())
            self.forward_button.setEnabled(enabled and view.history().canGoForward())
            self.reload_button.setEnabled(enabled)
            self.home_button.setEnabled(enabled)

        def handle_initial_command(self, line: str) -> None:
            try:
                payload = json.loads(line)
                raw_url = payload.get("url", ABOUT_BLANK)
                url = normalize_browser_url(raw_url, allow_about_blank=True)
            except (BrowserInputError, TypeError, ValueError, json.JSONDecodeError):
                self._set_status("Endereço inicial inválido; aberta uma nova guia.")
                return
            view = self.current_view()
            if view is not None and url != ABOUT_BLANK:
                self._set_url(view, url)

        def closeEvent(self, event) -> None:
            active_pages = []
            for index in range(self.tabs.count() - 1, -1, -1):
                view = self.tabs.widget(index)
                self.tabs.removeTab(index)
                if view is not None:
                    active_pages.append(view.page())
                    view.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            for page in active_pages:
                page.deleteLater()
                if page in self._pages:
                    self._pages.remove(page)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.profile.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            super().closeEvent(event)


else:

    class BrowserWindow:  # pragma: no cover - apenas mensagem para instalação ausente
        def __init__(self):
            raise RuntimeError(MISSING_ENGINE_MESSAGE)


def _listen_for_initial_command(window: BrowserWindow) -> None:
    """Lê uma única mensagem de stdin sem bloquear o loop Qt."""

    bridge = _InitialCommandBridge()
    bridge.command_received.connect(window.handle_initial_command)
    window._initial_command_bridge = bridge

    def read_once() -> None:
        try:
            line = sys.stdin.readline()
        except (OSError, ValueError):
            return
        if line:
            bridge.command_received.emit(line)

    thread = threading.Thread(target=read_once, name="browser-command", daemon=True)
    thread.start()


def main() -> int:
    if not QT_WEBENGINE_AVAILABLE:
        sys.stderr.write(MISSING_ENGINE_MESSAGE + "\n")
        return 2

    # Deve ser definido antes de criar QApplication para o WebEngine funcionar
    # de forma consistente em instalações Windows com Qt6.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("Navegador")
    window = BrowserWindow()
    _listen_for_initial_command(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
