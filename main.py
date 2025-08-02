import sys
import asyncio
import sqlite3
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QListWidget, QMessageBox, QListWidgetItem, QScrollArea, QFileDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from jup_swap import JupSwap

DB_PATH = "./pairs.db"
PK_PATH = "./private_key.txt"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inputMint TEXT,
            outputMint TEXT,
            amount INTEGER,
            slippageBps INTEGER,
            priorityFeeLamports INTEGER
        )
    """)
    conn.commit()
    conn.close()

class Worker(QThread):
    result_signal = pyqtSignal(str)
    balance_signal = pyqtSignal(str)

    def __init__(self, swap, inputMint, outputMint, amount, slippageBps, priorityFeeLamports):
        super().__init__()
        self.swap = swap
        self.inputMint = inputMint
        self.outputMint = outputMint
        self.amount = amount
        self.slippageBps = slippageBps
        self.priorityFeeLamports = priorityFeeLamports

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.swap.fetch_and_execute(
                    inputMint=self.inputMint,
                    outputMint=self.outputMint,
                    amount=self.amount,
                    slippageBps=self.slippageBps,
                    priorityFeeLamports=self.priorityFeeLamports
                )
            )
            self.result_signal.emit(str(result))
        except Exception as e:
            self.result_signal.emit(f"Worker error: {str(e)}")

class BalanceWorker(QThread):
    balance_signal = pyqtSignal(str, int)

    def __init__(self, swap, mint):
        super().__init__()
        self.swap = swap
        self.mint = mint

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
         #   print(self.mint)
            if self.mint != "So11111111111111111111111111111111111111112":
                balance = loop.run_until_complete(self.swap.get_token_balance(self.mint))
            else:
                balance = loop.run_until_complete(self.swap.get_balance())
            amount = 0
            try:
                if hasattr(balance, "value") and hasattr(balance.value, "amount"):
                    amount = int(balance.value.amount)
                elif isinstance(balance, dict):
                    amount = int(balance.get("result", {}).get("value", {}).get("amount", 0))
                elif hasattr(balance, "value"):
                    amount = int(balance.value)
            except Exception:
                amount = 0
            self.balance_signal.emit(self.mint, amount)
        except Exception as e:
            # Ошибка потока, выводим в консоль, не закрываем приложение
            main_win = None
            parent = self.parent()
            while parent and not isinstance(parent, MainWindow):
                parent = parent.parent()
            main_win = parent
            if main_win:
                main_win.console.append(f"BalanceWorker error: {str(e)}")
            self.balance_signal.emit(self.mint, 0)

class PairWidget(QWidget):
    def __init__(self, swap, pair, parent=None):
        super().__init__(parent)
        self.swap = swap
        self.pair = list(pair)
        self.current_balance = 0
        self.worker = None
        self.balance_thread = None
        self.balance_timer = None
        self.init_ui()

    def get_main_window(self):
        # Поиск главного окна для доступа к консоли
        parent = self.parent()
        while parent and not isinstance(parent, MainWindow):
            parent = parent.parent()
        return parent

    def get_console(self):
        # Поиск консоли главного окна
        main_win = self.get_main_window()
        if main_win:
            return main_win.console
        return None

    def init_ui(self):
        layout = QHBoxLayout()
        # Editable fields for all parameters
        self.id_label = QLabel(f"ID:{self.pair[0]}")
        layout.addWidget(self.id_label)
        self.inputMint_edit = QLineEdit(self.pair[1])
        self.inputMint_edit.setFixedWidth(180)
        layout.addWidget(QLabel("Input:"))
        layout.addWidget(self.inputMint_edit)
        self.outputMint_edit = QLineEdit(self.pair[2])
        self.outputMint_edit.setFixedWidth(180)
        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self.outputMint_edit)
        self.amount_edit = QLineEdit(str(self.pair[3]))
        self.amount_edit.setFixedWidth(80)
        layout.addWidget(QLabel("Amount:"))
        layout.addWidget(self.amount_edit)
        self.slippage_edit = QLineEdit(str(self.pair[4]))
        self.slippage_edit.setFixedWidth(60)
        layout.addWidget(QLabel("Slippage:"))
        layout.addWidget(self.slippage_edit)
        self.priority_edit = QLineEdit(str(self.pair[5]))
        self.priority_edit.setFixedWidth(80)
        layout.addWidget(QLabel("Priority:"))
        layout.addWidget(self.priority_edit)

        self.balance_label = QLabel("Balance: ...")
        layout.addWidget(self.balance_label)
        self.update_btn = QPushButton("Update Balance")
        self.update_btn.clicked.connect(self.update_balance)
        layout.addWidget(self.update_btn)

        # Sell controls (for non-SOL tokens)
        if self.pair[1] != "So11111111111111111111111111111111111111112":
            self.percent_edit = QLineEdit("100")
            self.percent_edit.setFixedWidth(40)
            layout.addWidget(QLabel("Sell %:"))
            layout.addWidget(self.percent_edit)
            self.sell_btn = QPushButton("Sell")
            self.sell_btn.clicked.connect(self.sell_token)
            layout.addWidget(self.sell_btn)
            # Автообновление баланса
            self.balance_timer = QTimer(self)
            self.balance_timer.timeout.connect(self.update_balance)
            self.balance_timer.start(10000)  # 3 секунды
        else:
            # BUY button for SOL
            self.buy_btn = QPushButton("Buy")
            self.buy_btn.clicked.connect(self.buy_token)
            layout.addWidget(self.buy_btn)

        # Save changes button
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_changes)
        layout.addWidget(self.save_btn)

        # Delete button
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_pair)
        layout.addWidget(self.delete_btn)

        self.setLayout(layout)

    def update_balance(self):
        mint = self.inputMint_edit.text().strip()
        console = self.get_console()
        if console:
            console.append(f"Updating balance for {mint}...")
        try:
            if not mint:
                if console:
                    console.append("Input Mint required!")
                return
            
            if not self.swap:
                if console:
                    console.append("Set private key first!")
                return
            # Безопасно останавливаем предыдущий поток
            try:
                if hasattr(self, "balance_worker") and self.balance_worker is not None and self.balance_worker.isRunning():
                    self.balance_worker.quit()
                    self.balance_worker.wait()
            except Exception as e:
                if console:
                    console.append(f"Thread stop error: {str(e)}")
            if console:
                console.append(f"Getting balance for {mint}...")
            self.balance_worker = BalanceWorker(self.swap, mint)
            self.balance_worker.balance_signal.connect(self.show_balance)
            self.balance_worker.finished.connect(lambda: console.append(f"BalanceWorker for {mint} finished") if console else None)
            self.balance_worker.start()
        except Exception as e:
            if console:
                console.append(f"Update balance error: {str(e)}")

    def cleanup_balance_thread(self):
        self.balance_thread = None

    def show_balance(self, mint, amount):
        self.balance_label.setText(f"Balance: {amount}")
        self.current_balance = amount

    def sell_token(self):
        percent = float(self.percent_edit.text())
        # Баланс всегда актуальный, учитываем Sell%
        amount = int(self.current_balance * percent / 100)
        inputMint = self.inputMint_edit.text().strip()
        outputMint = self.outputMint_edit.text().strip()
        slippage = int(self.slippage_edit.text())
        priority = int(self.priority_edit.text())
        main_win = self.get_main_window()
        if main_win:
            main_win.console.append(f"Selling {amount} of {inputMint} ({percent}%)")
            if self.worker is not None and self.worker.isRunning():
                self.worker.quit()
                self.worker.wait()
            self.worker = Worker(
                self.swap,
                inputMint, outputMint, amount,
                slippage, priority
            )
            self.worker.result_signal.connect(main_win.console.append)
            self.worker.finished.connect(self.cleanup_worker)
            self.worker.start()

    def buy_token(self):
        amount = int(self.amount_edit.text())
        inputMint = self.inputMint_edit.text().strip()
        outputMint = self.outputMint_edit.text().strip()
        slippage = int(self.slippage_edit.text())
        priority = int(self.priority_edit.text())
        main_win = self.get_main_window()
        if main_win:
            main_win.console.append(f"Buying {amount} of {inputMint}")
            if self.worker is not None and self.worker.isRunning():
                self.worker.quit()
                self.worker.wait()
            self.worker = Worker(
                self.swap,
                inputMint, outputMint, amount,
                slippage, priority
            )
            self.worker.result_signal.connect(main_win.console.append)
            self.worker.finished.connect(self.cleanup_worker)
            self.worker.start()

    def cleanup_worker(self):
        self.worker = None

    def save_changes(self):
        # Сохраняем изменения в БД
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE pairs SET inputMint=?, outputMint=?, amount=?, slippageBps=?, priorityFeeLamports=? WHERE id=?",
            (
                self.inputMint_edit.text().strip(),
                self.outputMint_edit.text().strip(),
                int(self.amount_edit.text()),
                int(self.slippage_edit.text()),
                int(self.priority_edit.text()),
                self.pair[0]
            )
        )
        conn.commit()
        conn.close()
        main_win = self.get_main_window()
        if main_win:
            main_win.console.append(f"Pair {self.pair[0]} updated.")

    def delete_pair(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM pairs WHERE id=?", (self.pair[0],))
        conn.commit()
        conn.close()
        main_win = self.get_main_window()
        if main_win:
            main_win.console.append(f"Pair {self.pair[0]} deleted.")
            main_win.load_pairs()

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.swap = None
        self.private_key_str = ''
        self.setWindowTitle("Jupiter Swap GUI")
        self.setGeometry(100, 100, 900, 600)
        self.init_ui()
        init_db()
        self.load_private_key()
        self.load_pairs()

    def init_ui(self):
        layout = QVBoxLayout()

        # Private key input
        pk_layout = QHBoxLayout()
        self.pk_edit = QLineEdit()
        self.pk_edit.setEchoMode(QLineEdit.Password)
        self.pk_edit.setPlaceholderText("Enter your private key")
        self.pk_btn = QPushButton("Set Private Key")
        self.pk_btn.clicked.connect(self.set_private_key)
        pk_layout.addWidget(QLabel("Private Key:"))
        pk_layout.addWidget(self.pk_edit)
        pk_layout.addWidget(self.pk_btn)
        layout.addLayout(pk_layout)

        # Token input
        form_layout = QHBoxLayout()
        self.inputMint_edit = QLineEdit()
        self.inputMint_edit.setPlaceholderText("Input Mint")
        self.outputMint_edit = QLineEdit()
        self.outputMint_edit.setPlaceholderText("Output Mint")
        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("Amount")
        self.slippage_edit = QLineEdit("300")
        self.slippage_edit.setPlaceholderText("Slippage Bps")
        self.priority_edit = QLineEdit("500000")
        self.priority_edit.setPlaceholderText("Priority Fee Lamports")
        self.balance_btn = QPushButton("Update Balance")
        self.balance_btn.clicked.connect(self.update_balance)
        form_layout.addWidget(QLabel("Input Mint:"))
        form_layout.addWidget(self.inputMint_edit)
        form_layout.addWidget(QLabel("Output Mint:"))
        form_layout.addWidget(self.outputMint_edit)
        form_layout.addWidget(QLabel("Amount:"))
        form_layout.addWidget(self.amount_edit)
        form_layout.addWidget(self.balance_btn)
        form_layout.addWidget(QLabel("Slippage:"))
        form_layout.addWidget(self.slippage_edit)
        form_layout.addWidget(QLabel("Priority Fee:"))
        form_layout.addWidget(self.priority_edit)
        layout.addLayout(form_layout)

        # Pair widgets area (scrollable)
        self.pair_area = QScrollArea()
        self.pair_area.setWidgetResizable(True)
        self.pair_container = QWidget()
        self.pair_layout = QVBoxLayout()
        self.pair_container.setLayout(self.pair_layout)
        self.pair_area.setWidget(self.pair_container)
        layout.addWidget(QLabel("Token pairs:"))
        layout.addWidget(self.pair_area)

        # Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add Pair")
        self.add_btn.clicked.connect(self.add_pair)
        self.run_btn = QPushButton("Run All Swaps")
        self.run_btn.clicked.connect(self.run_all_swaps)
        self.import_btn = QPushButton("Import Pairs")
        self.import_btn.clicked.connect(self.import_pairs)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.import_btn)
        layout.addLayout(btn_layout)

        # Console
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(QLabel("Console:"))
        layout.addWidget(self.console)

        self.setLayout(layout)

    def set_private_key(self):
        pk = self.pk_edit.text().strip()
        if not pk:
            QMessageBox.warning(self, "Error", "Private key required!")
            return
        self.private_key_str = pk
        self.swap = JupSwap(private_key_str=pk)
        # Save private key to file
        with open(PK_PATH, "w") as f:
            f.write(pk)
        self.console.append("Private key set and saved.")

    def load_private_key(self):
        if os.path.exists(PK_PATH):
            with open(PK_PATH, "r") as f:
                pk = f.read().strip()
                if pk:
                    self.private_key_str = pk
                    self.pk_edit.setText(pk)
                    self.swap = JupSwap(private_key_str=pk)
                    self.console.append("Private key loaded from file.")

    def add_pair(self):
        inputMint = self.inputMint_edit.text().strip()
        outputMint = self.outputMint_edit.text().strip()
        amount = self.amount_edit.text().strip()
        slippage = self.slippage_edit.text().strip()
        priority = self.priority_edit.text().strip()
        if not inputMint or not outputMint or not amount:
            QMessageBox.warning(self, "Error", "Fill all fields!")
            return
        if not self.swap:
            QMessageBox.warning(self, "Error", "Set private key first!")
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO pairs (inputMint, outputMint, amount, slippageBps, priorityFeeLamports) VALUES (?, ?, ?, ?, ?)",
                  (inputMint, outputMint, int(amount), int(slippage), int(priority)))
        conn.commit()
        conn.close()
        self.load_pairs()
        self.console.append(f"Pair added: {inputMint} -> {outputMint} amount={amount}")

    def load_pairs(self):
        # Отображаем пары как виджеты, а не как элементы списка
        # Очищаем layout
        while self.pair_layout.count():
            item = self.pair_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.pair_widgets = []
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for row in c.execute("SELECT id, inputMint, outputMint, amount, slippageBps, priorityFeeLamports FROM pairs"):
            widget = PairWidget(self.swap, row, parent=self.pair_container)
            self.pair_widgets.append(widget)
            self.pair_layout.addWidget(widget)
        conn.close()

    def run_all_swaps(self):
        # Останавливаем все предыдущие воркеры, если они есть
        for widget in self.pair_widgets:
            try:
                if hasattr(widget, "worker") and widget.worker is not None and widget.worker.isRunning():
                    widget.worker.quit()
                    widget.worker.wait()
                inputMint = widget.inputMint_edit.text().strip()
                outputMint = widget.outputMint_edit.text().strip()
                amount = int(widget.amount_edit.text())
                slippage = int(widget.slippage_edit.text())
                priority = int(widget.priority_edit.text())
                # Учитываем процент продажи если есть
                if hasattr(widget, "percent_edit"):
                    try:
                        percent = float(widget.percent_edit.text())
                        amount = int(widget.current_balance * percent / 100)
                    except Exception:
                        percent = 100
                self.console.append(
                    f"Running swap: {inputMint} → {outputMint} | Amount: {amount} | Slippage: {slippage} | Priority: {priority}"
                )
                widget.worker = Worker(self.swap, inputMint, outputMint, amount, slippage, priority)
                widget.worker.result_signal.connect(self.console.append)
                widget.worker.finished.connect(widget.cleanup_worker)
                widget.worker.start()
            except Exception as e:
                self.console.append(f"run_all_swaps error: {str(e)}")

    def update_balance(self):
        mint = self.inputMint_edit.text().strip()
        self.console.append(f"Updating balance for {mint}...")
        try:
            if not mint:
                QMessageBox.warning(self, "Error", "Input Mint required!")
                return
           
            if not self.swap:
                QMessageBox.warning(self, "Error", "Set private key first!")
                return
            # Безопасно останавливаем предыдущий поток
            try:
                if hasattr(self, "balance_worker") and self.balance_worker is not None and self.balance_worker.isRunning():
                    self.balance_worker.quit()
                    self.balance_worker.wait()
            except Exception as e:
                self.console.append(f"Thread stop error: {str(e)}")
            self.console.append(f"Getting balance for {mint}...")
            self.balance_worker = BalanceWorker(self.swap, mint)
            self.balance_worker.balance_signal.connect(self.show_balance)
            self.balance_worker.finished.connect(lambda: self.console.append(f"BalanceWorker for {mint} finished"))
            self.balance_worker.start()
        except Exception as e:
            self.console.append(f"Update balance error: {str(e)}")

    def show_balance(self, mint, amount):
        self.console.append(f"Balance for {mint}: {amount}")
        self.amount_edit.setText(str(amount))

    def import_pairs(self):
        # Пример формата:
        # inputMint,outputMint,amount,slippageBps,priorityFeeLamports
        # So11111111111111111111111111111111111111112,EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v,10000,300,500000
        # JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN,So11111111111111111111111111111111111111112,5000,200,400000
        fname, _ = QFileDialog.getOpenFileName(self, "Import pairs from file", "", "Text Files (*.txt);;All Files (*)")
        if not fname:
            return
        try:
            with open(fname, "r") as f:
                lines = f.readlines()
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            imported = 0
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",")
                if len(parts) < 5:
                    self.console.append(f"Skipped line (wrong format): {line}")
                    continue
                inputMint, outputMint, amount, slippage, priority = parts[:5]
                try:
                    c.execute("INSERT INTO pairs (inputMint, outputMint, amount, slippageBps, priorityFeeLamports) VALUES (?, ?, ?, ?, ?)",
                              (inputMint, outputMint, int(amount), int(slippage), int(priority)))
                    imported += 1
                except Exception as e:
                    self.console.append(f"Import error: {str(e)}")
            conn.commit()
            conn.close()
            self.load_pairs()
            self.console.append(f"Imported {imported} pairs from {fname}")
        except Exception as e:
            self.console.append(f"Import failed: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

