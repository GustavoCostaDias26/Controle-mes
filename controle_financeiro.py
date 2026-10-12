import calendar
import csv
import sqlite3
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk


DB_PATH = Path(__file__).resolve().with_name("financas.db")
BG = "#F3F6FB"
CARD = "#FFFFFF"
NAVY = "#17243A"
MUTED = "#8290A5"
TEXT = "#24334A"
ACCENT = "#4F7CFF"
GREEN = "#1FA97A"
RED = "#E46666"


def ensure_payment_column(connection):
    cursor = connection.cursor()
    columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(parcelas)").fetchall()
    }
    if "valor_pago" not in columns:
        cursor.execute(
            "ALTER TABLE parcelas ADD COLUMN valor_pago REAL NOT NULL DEFAULT 0"
        )
        cursor.execute("""
        UPDATE parcelas
        SET valor_pago = ROUND(
            valor_total * MIN(parcelas_pagas, total_parcelas) / total_parcelas, 2
        )
        WHERE parcelas_pagas > 0 AND total_parcelas > 0
        """)
        connection.commit()
    if "valor_parcela" not in columns:
        cursor.execute(
            "ALTER TABLE parcelas ADD COLUMN valor_parcela REAL NOT NULL DEFAULT 0"
        )
        cursor.execute("""
        UPDATE parcelas
        SET valor_parcela = ROUND(valor_total / total_parcelas, 2)
        WHERE total_parcelas > 0
        """)
        connection.commit()


conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = ON")
cursor.execute("""
CREATE TABLE IF NOT EXISTS parcelas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT,
    valor_total REAL,
    total_parcelas INTEGER,
    parcelas_pagas INTEGER,
    vencimento TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS gastos_aleatorios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT,
    valor REAL,
    data TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS receitas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT,
    valor REAL,
    data TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS pagamentos_parcelas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parcela_id INTEGER NOT NULL REFERENCES parcelas(id) ON DELETE CASCADE,
    valor REAL NOT NULL,
    data TEXT NOT NULL
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS investimentos_aportes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL,
    data TEXT NOT NULL
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS investimentos_saldos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor REAL NOT NULL,
    data TEXT NOT NULL
)
""")
conn.commit()
ensure_payment_column(conn)


def format_currency(value):
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def parse_currency(value, allow_zero=False):
    value = value.strip().replace("R$", "").replace(" ", "")
    if not value:
        raise ValueError("Informe um valor válido, por exemplo: 250,00.")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        amount = float(value)
    except ValueError as error:
        raise ValueError("Informe um valor válido, por exemplo: 250,00.") from error
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError(
            "Informe um valor maior que zero."
            if not allow_zero else "Informe um valor igual ou maior que zero."
        )
    return amount


def parse_date(value):
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError as error:
        raise ValueError("Informe uma data válida no formato dd/mm/aaaa.") from error


def paid_installment_count(amount_paid, installment_amount, installment_count):
    installment_cents = round(installment_amount * 100)
    if installment_cents <= 0:
        return 0
    paid_cents = round(amount_paid * 100)
    return min(installment_count, paid_cents // installment_cents)


class FinanceApp:
    def __init__(self, window):
        self.root = window
        self.root.title("Organiza • Controle financeiro")
        self.root.geometry("1280x820")
        self.root.minsize(1000, 680)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._configure_styles()
        self._build_shell()
        self._build_dashboard()
        self._build_installments()
        self._build_expenses()
        self._build_income()
        self._build_savings()
        self.show_page("dashboard")
        self.refresh_all()

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=CARD,
            foreground=TEXT,
            fieldbackground=CARD,
            rowheight=38,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#EDF1F7",
            foreground="#56657B",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padding=(10, 10),
        )
        style.map("Treeview", background=[("selected", "#E5EDFF")],
                  foreground=[("selected", TEXT)])
        style.configure("Vertical.TScrollbar", background="#DCE3ED", troughcolor=BG,
                        borderwidth=0, arrowsize=12)

    def _build_shell(self):
        self.sidebar = tk.Frame(self.root, bg=NAVY, width=228)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = tk.Frame(self.sidebar, bg=NAVY)
        brand.pack(fill="x", padx=22, pady=(28, 36))
        tk.Label(brand, text="◈", bg=NAVY, fg="#80A1FF",
                 font=("Segoe UI", 22, "bold")).pack(side="left")
        brand_text = tk.Frame(brand, bg=NAVY)
        brand_text.pack(side="left", padx=(10, 0))
        tk.Label(brand_text, text="organiza", bg=NAVY, fg="white",
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(brand_text, text="FINANÇAS PESSOAIS", bg=NAVY, fg="#91A0B8",
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(2, 0))

        tk.Label(self.sidebar, text="MENU PRINCIPAL", bg=NAVY, fg="#71809A",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=24, pady=(0, 10))
        self.nav_buttons = {}
        for key, label, icon in (
            ("dashboard", "Visão geral", "⌂"),
            ("installments", "Contas parceladas", "▤"),
            ("expenses", "Gastos avulsos", "↗"),
            ("income", "Valores recebidos", "+"),
            ("savings", "Investimentos", "R$"),
        ):
            button = tk.Button(
                self.sidebar,
                text=f"  {icon}     {label}",
                command=lambda page=key: self.show_page(page),
                anchor="w",
                padx=18,
                pady=12,
                bd=0,
                relief="flat",
                cursor="hand2",
                bg=NAVY,
                fg="#B8C3D5",
                activebackground="#253651",
                activeforeground="white",
                font=("Segoe UI", 10),
            )
            button.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[key] = button

        tk.Label(
            self.sidebar,
            text="Seu dinheiro, mais\nfácil de acompanhar.",
            bg=NAVY,
            fg="#91A0B8",
            justify="left",
            font=("Segoe UI", 9),
        ).pack(side="bottom", anchor="w", padx=24, pady=24)

        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)
        self.page_host = tk.Frame(self.content, bg=BG)
        self.page_host.pack(fill="both", expand=True, padx=30, pady=26)
        self.pages = {}

    def _page(self, key, title, subtitle):
        page = tk.Frame(self.page_host, bg=BG)
        self.pages[key] = page
        heading = tk.Frame(page, bg=BG)
        heading.pack(fill="x", pady=(0, 24))
        tk.Label(heading, text=title, bg=BG, fg=TEXT,
                 font=("Segoe UI", 23, "bold")).pack(anchor="w")
        tk.Label(heading, text=subtitle, bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(5, 0))
        return page

    def show_page(self, page_name):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[page_name].pack(fill="both", expand=True)
        for key, button in self.nav_buttons.items():
            selected = key == page_name
            button.configure(
                bg="#2B3C59" if selected else NAVY,
                fg="white" if selected else "#B8C3D5",
            )

    @staticmethod
    def _card(parent, padx=20, pady=18):
        return tk.Frame(parent, bg=CARD, padx=padx, pady=pady,
                        highlightthickness=1, highlightbackground="#E8EDF4")

    def _build_dashboard(self):
        page = self._page(
            "dashboard",
            "Visão geral",
            "Acompanhe suas contas e despesas em um só lugar.",
        )

        self.summary_row = tk.Frame(page, bg=BG)
        self.summary_row.pack(fill="x")
        for column in range(4):
            self.summary_row.columnconfigure(column, weight=1, uniform="summary")
        self.summary_values = {}
        summary_data = (
            ("installments", "TOTAL PARCELADO", ACCENT, "▤"),
            ("paid", "VALOR JÁ PAGO", GREEN, "✓"),
            ("remaining", "FALTA PAGAR", RED, "◷"),
            ("expenses", "GASTOS AVULSOS", "#8B6FE8", "↗"),
        )
        for column, (key, title, color, icon) in enumerate(summary_data):
            card = self._card(self.summary_row)
            card.grid(row=0, column=column, sticky="nsew",
                      padx=(0 if column == 0 else 8, 8 if column < 3 else 0))
            tk.Label(card, text=title, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            line = tk.Frame(card, bg=CARD)
            line.pack(fill="x", pady=(12, 3))
            value = tk.Label(line, text="R$ 0,00", bg=CARD, fg=TEXT,
                             font=("Segoe UI", 15, "bold"))
            value.pack(side="left")
            tk.Label(line, text=icon, bg=CARD, fg=color,
                     font=("Segoe UI", 16, "bold")).pack(side="right")
            self.summary_values[key] = value

        lower = tk.Frame(page, bg=BG)
        lower.pack(fill="both", expand=True, pady=(20, 0))
        lower.columnconfigure(0, weight=3, uniform="dashboard")
        lower.columnconfigure(1, weight=2, uniform="dashboard")
        lower.rowconfigure(0, weight=1)

        chart_card = self._card(lower, padx=20, pady=18)
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        chart_heading = tk.Frame(chart_card, bg=CARD)
        chart_heading.pack(fill="x")
        tk.Label(chart_heading, text="Despesas ao longo do tempo", bg=CARD,
                 fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(chart_heading, text="Gastos avulsos • últimos 6 meses",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        self.chart = tk.Canvas(chart_card, bg=CARD, highlightthickness=0, height=260)
        self.chart.pack(fill="both", expand=True, pady=(14, 0))
        self.chart.bind(
            "<Configure>",
            lambda event: event.widget.after_idle(self._draw_chart),
        )

        alert_card = self._card(lower, padx=20, pady=18)
        alert_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        alert_heading = tk.Frame(alert_card, bg=CARD)
        alert_heading.pack(fill="x")
        tk.Label(alert_heading, text="Próximos vencimentos", bg=CARD,
                 fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(alert_heading, text="Contas que vencem nos próximos 5 dias",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        self.alert_list = tk.Frame(alert_card, bg=CARD)
        self.alert_list.pack(fill="both", expand=True, pady=(15, 0))

    def _build_installments(self):
        page = self._page(
            "installments",
            "Contas parceladas",
            "Cadastre compromissos, acompanhe as parcelas e mantenha tudo organizado.",
        )
        form = self._card(page, padx=20, pady=16)
        form.pack(fill="x", pady=(0, 16))
        tk.Label(form, text="Adicionar conta", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=5,
                                                    sticky="w", pady=(0, 12))
        self.installment_fields = {}
        fields = (
            ("description", "Descrição", "Ex.: Notebook"),
            ("value", "Valor fixo da parcela (R$)", "0,00"),
            ("count", "Total de parcelas", "12"),
            ("paid", "Parcelas pagas", "0"),
            ("due", "Vencimento (dd/mm/aaaa)", date.today().strftime("%d/%m/%Y")),
        )
        for column, (key, label, initial) in enumerate(fields):
            wrapper = tk.Frame(form, bg=CARD)
            wrapper.grid(row=1, column=column, sticky="ew",
                         padx=(0 if column == 0 else 10, 0), pady=(0, 12))
            tk.Label(wrapper, text=label, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
            variable = tk.StringVar(value=initial if key == "due" else "")
            entry = ttk.Entry(wrapper, textvariable=variable, font=("Segoe UI", 10))
            entry.pack(fill="x", ipady=7)
            self.installment_fields[key] = variable
            form.columnconfigure(column, weight=1)
        tk.Button(
            form,
            text="＋  Adicionar conta",
            command=self.add_installment,
            bg=ACCENT,
            fg="white",
            activebackground="#3D68E7",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=10,
        ).grid(row=2, column=0, columnspan=5, sticky="e")

        self.installment_search = tk.StringVar()
        self.installment_search.trace_add("write", lambda *_: self.refresh_installments())
        self.installment_sort = tk.StringVar(value="Mais recentes")
        self.installment_sort.trace_add("write", lambda *_: self.refresh_installments())
        self.installment_tree = self._build_table(
            page,
            "Contas cadastradas",
            self.installment_search,
            (
                "ID", "Descrição", "Valor/parcela", "Valor total", "Valor pago",
                "Falta pagar", "Total", "Pagas", "Pendentes", "Vencimento",
            ),
            (40, 145, 100, 105, 100, 100, 50, 50, 65, 95),
        )
        self.installment_tree.bind("<Double-1>", self._edit_due_date_from_cell)

    def _build_expenses(self):
        page = self._page(
            "expenses",
            "Gastos avulsos",
            "Registre despesas do dia a dia e veja para onde seu dinheiro está indo.",
        )
        form = self._card(page, padx=20, pady=16)
        form.pack(fill="x", pady=(0, 16))
        tk.Label(form, text="Registrar gasto", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3,
                                                    sticky="w", pady=(0, 12))
        self.expense_fields = {}
        fields = (
            ("description", "Descrição", "Ex.: Mercado"),
            ("value", "Valor (R$)", "0,00"),
            ("date", "Data (dd/mm/aaaa)", date.today().strftime("%d/%m/%Y")),
        )
        for column, (key, label, initial) in enumerate(fields):
            wrapper = tk.Frame(form, bg=CARD)
            wrapper.grid(row=1, column=column, sticky="ew",
                         padx=(0 if column == 0 else 12, 0), pady=(0, 12))
            tk.Label(wrapper, text=label, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
            variable = tk.StringVar(value=initial if key == "date" else "")
            ttk.Entry(wrapper, textvariable=variable, font=("Segoe UI", 10)).pack(
                fill="x", ipady=7
            )
            self.expense_fields[key] = variable
            form.columnconfigure(column, weight=1)
        tk.Button(
            form,
            text="＋  Registrar gasto",
            command=self.add_expense,
            bg=GREEN,
            fg="white",
            activebackground="#178A64",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=10,
        ).grid(row=2, column=0, columnspan=3, sticky="e")

        self.expense_search = tk.StringVar()
        self.expense_search.trace_add("write", lambda *_: self.refresh_expenses())
        self.expense_tree = self._build_table(
            page,
            "Histórico de gastos",
            self.expense_search,
            ("ID", "Descrição", "Valor", "Data"),
            (70, 360, 170, 150),
        )

    def _build_income(self):
        page = self._page(
            "income",
            "Valores recebidos",
            "Registre o dinheiro que entrou e acompanhe o total recebido em cada mês.",
        )
        form = self._card(page, padx=20, pady=16)
        form.pack(fill="x", pady=(0, 16))
        tk.Label(form, text="Registrar valor recebido", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3,
                                                    sticky="w", pady=(0, 12))
        self.income_fields = {}
        fields = (
            ("description", "Descrição", "Ex.: Salário"),
            ("value", "Valor recebido (R$)", "0,00"),
            ("date", "Data (dd/mm/aaaa)", date.today().strftime("%d/%m/%Y")),
        )
        for column, (key, label, initial) in enumerate(fields):
            wrapper = tk.Frame(form, bg=CARD)
            wrapper.grid(row=1, column=column, sticky="ew",
                         padx=(0 if column == 0 else 12, 0), pady=(0, 12))
            tk.Label(wrapper, text=label, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
            variable = tk.StringVar(value=initial if key == "date" else "")
            ttk.Entry(wrapper, textvariable=variable, font=("Segoe UI", 10)).pack(
                fill="x", ipady=7
            )
            self.income_fields[key] = variable
            form.columnconfigure(column, weight=1)
        tk.Button(
            form,
            text="＋  Registrar recebimento",
            command=self.add_income,
            bg=GREEN,
            fg="white",
            activebackground="#178A64",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=10,
        ).grid(row=2, column=0, columnspan=3, sticky="e")

        summary = self._card(page, padx=20, pady=14)
        summary.pack(fill="x", pady=(0, 16))
        tk.Label(summary, text="RECEBIDO NESTE MÊS", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.current_month_income = tk.Label(
            summary, text="R$ 0,00", bg=CARD, fg=GREEN,
            font=("Segoe UI", 18, "bold"),
        )
        self.current_month_income.pack(anchor="w", pady=(6, 0))

        self.income_search = tk.StringVar()
        self.income_search.trace_add("write", lambda *_: self.refresh_income())
        self.income_tree = self._build_table(
            page,
            "Histórico de recebimentos",
            self.income_search,
            ("ID", "Descrição", "Valor recebido", "Data"),
            (70, 360, 170, 150),
        )

    def _build_savings(self):
        page = self._page(
            "savings",
            "Investimentos",
            "Registre seus aportes e atualize o saldo da carteira. A variação compara "
            "o saldo informado com os aportes feitos até aquela data.",
        )
        page_canvas = tk.Canvas(page, bg=BG, highlightthickness=0)
        page_scrollbar = ttk.Scrollbar(
            page, orient="vertical", command=page_canvas.yview
        )
        page_canvas.configure(yscrollcommand=page_scrollbar.set)
        page_canvas.pack(side="left", fill="both", expand=True)
        page_scrollbar.pack(side="right", fill="y")
        content = tk.Frame(page_canvas, bg=BG)
        content_window = page_canvas.create_window(
            (0, 0), window=content, anchor="nw"
        )
        content.bind(
            "<Configure>",
            lambda event: page_canvas.configure(
                scrollregion=(0, 0, event.width, event.height)
            ),
        )
        page_canvas.bind(
            "<Configure>",
            lambda event: page_canvas.itemconfigure(
                content_window, width=event.width
            ),
        )

        forms = tk.Frame(content, bg=BG)
        forms.pack(fill="x", pady=(0, 16))
        forms.columnconfigure(0, weight=1, uniform="investment_forms")
        forms.columnconfigure(1, weight=1, uniform="investment_forms")

        contribution_form = self._card(forms, padx=16, pady=14)
        contribution_form.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(contribution_form, text="Registrar aporte", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 10))
        self.investment_fields = {}
        for key, label, initial in (
            ("description", "Investimento", ""),
            ("value", "Valor aplicado (R$)", ""),
            ("date", "Data do aporte", date.today().strftime("%d/%m/%Y")),
        ):
            tk.Label(contribution_form, text=label, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
            variable = tk.StringVar(value=initial)
            ttk.Entry(
                contribution_form, textvariable=variable, font=("Segoe UI", 10)
            ).pack(fill="x", ipady=5, pady=(0, 8))
            self.investment_fields[key] = variable
        tk.Button(
            contribution_form, text="＋  Registrar aporte",
            command=self.add_investment_contribution,
            bg=GREEN, fg="white", activebackground="#178A64",
            activeforeground="white", relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9, "bold"), padx=14, pady=8,
        ).pack(anchor="e")

        balance_form = self._card(forms, padx=16, pady=14)
        balance_form.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        tk.Label(balance_form, text="Atualizar saldo da carteira", bg=CARD,
                 fg=TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 10))
        tk.Label(balance_form, text="Valor total atual dos investimentos (R$)",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(
                     anchor="w", pady=(0, 4)
                 )
        self.investment_balance_value = tk.StringVar()
        ttk.Entry(
            balance_form, textvariable=self.investment_balance_value,
            font=("Segoe UI", 10),
        ).pack(fill="x", ipady=5, pady=(0, 8))
        tk.Label(balance_form, text="Data da atualização", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        self.investment_balance_date = tk.StringVar(
            value=date.today().strftime("%d/%m/%Y")
        )
        ttk.Entry(
            balance_form, textvariable=self.investment_balance_date,
            font=("Segoe UI", 10),
        ).pack(fill="x", ipady=5, pady=(0, 8))
        tk.Button(
            balance_form, text="Atualizar saldo",
            command=self.update_investment_balance,
            bg=ACCENT, fg="white", activebackground="#3D68E7",
            activeforeground="white", relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9, "bold"), padx=14, pady=8,
        ).pack(anchor="e")

        summary = tk.Frame(content, bg=BG)
        summary.pack(fill="x", pady=(0, 16))
        for column in range(3):
            summary.columnconfigure(column, weight=1, uniform="investment_summary")
        self.investment_summary = {}
        for column, (key, title, color) in enumerate((
            ("balance", "SALDO ATUAL", ACCENT),
            ("contributed", "TOTAL APORTADO", TEXT),
            ("change", "VARIAÇÃO", GREEN),
        )):
            card = self._card(summary, padx=16, pady=12)
            card.grid(row=0, column=column, sticky="nsew",
                      padx=(0 if column == 0 else 6, 6 if column < 2 else 0))
            tk.Label(card, text=title, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            value = tk.Label(card, text="R$ 0,00", bg=CARD, fg=color,
                             font=("Segoe UI", 16, "bold"))
            value.pack(anchor="w", pady=(6, 0))
            self.investment_summary[key] = value
            if key == "balance":
                self.investment_balance_updated = tk.Label(
                    card, text="Saldo ainda não informado", bg=CARD, fg=MUTED,
                    font=("Segoe UI", 8),
                )
                self.investment_balance_updated.pack(anchor="w", pady=(4, 0))

        wrapper = self._card(content, padx=18, pady=14)
        wrapper.pack(fill="both", expand=True)
        tk.Label(wrapper, text="Evolução mensal", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 10))
        table_frame = tk.Frame(wrapper, bg=CARD)
        table_frame.pack(fill="both", expand=True)
        columns = ("Mês", "Aportes do mês", "Total aportado", "Saldo informado", "Variação")
        self.savings_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        for column, width in zip(columns, (150, 155, 155, 155, 140)):
            self.savings_tree.heading(column, text=column)
            self.savings_tree.column(column, width=width, minwidth=100, anchor="center")
        scroll = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.savings_tree.yview
        )
        self.savings_tree.configure(yscrollcommand=scroll.set)
        self.savings_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.savings_tree.tag_configure("alternate", background="#F8FAFD")

        self.investment_search = tk.StringVar()
        self.investment_search.trace_add(
            "write", lambda *_: self.refresh_investment_contributions()
        )
        tk.Label(
            content,
            text="No histórico abaixo, selecione um aporte ou saldo para editar ou excluir.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 8))
        self.investment_tree = self._build_table(
            content,
            "Histórico de investimentos",
            self.investment_search,
            ("ID", "Tipo", "Descrição", "Valor", "Data"),
            (55, 95, 235, 150, 115),
        )
        self.investment_tree.bind(
            "<Double-1>", self._edit_investment_from_double_click
        )

    def _build_table(self, parent, title, search_var, columns, widths):
        wrapper = self._card(parent, padx=18, pady=16)
        wrapper.pack(fill="both", expand=True)
        toolbar = tk.Frame(wrapper, bg=CARD)
        toolbar.pack(fill="x", pady=(0, 12))
        tk.Label(toolbar, text=title, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(
            toolbar,
            text="Exportar CSV",
            command=lambda: self.export_table(title),
            bg="#EDF2FF",
            fg="#4569C8",
            activebackground="#DFE8FF",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
            padx=12,
            pady=8,
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            toolbar,
            text="Excluir selecionado",
            command=lambda: self.delete_selected(title),
            bg="#FFF0F0",
            fg=RED,
            activebackground="#FFE2E2",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
            padx=12,
            pady=8,
        ).pack(side="right", padx=(8, 0))
        if title == "Histórico de investimentos":
            tk.Button(
                toolbar,
                text="Editar selecionado",
                command=self.edit_selected_investment,
                bg="#EAF8F2",
                fg="#16825D",
                activebackground="#D7F2E6",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=12,
                pady=8,
            ).pack(side="right", padx=(8, 0))
        if title == "Contas cadastradas":
            tk.Button(
                toolbar,
                text="Alterar vencimento",
                command=self.edit_due_date,
                bg="#FFF8D8",
                fg="#92720A",
                activebackground="#FFF0A8",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=12,
                pady=8,
            ).pack(side="right", padx=(8, 0))
            tk.Button(
                toolbar,
                text="Registrar pagamento",
                command=self.register_payment,
                bg="#EAF8F2",
                fg="#16825D",
                activebackground="#D7F2E6",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=12,
                pady=8,
            ).pack(side="right", padx=(8, 0))
        search = ttk.Entry(toolbar, textvariable=search_var, width=25,
                           font=("Segoe UI", 9))
        search.pack(side="right", ipady=6)
        tk.Label(toolbar, text="⌕", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 13)).pack(side="right", padx=(0, 5))

        if title == "Contas cadastradas":
            sort_bar = tk.Frame(wrapper, bg=CARD)
            sort_bar.pack(fill="x", pady=(0, 10))
            tk.Label(
                sort_bar,
                text="Ordenar contas por:",
                bg=CARD,
                fg=MUTED,
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(0, 8))
            ttk.Combobox(
                sort_bar,
                textvariable=self.installment_sort,
                values=(
                    "Mais recentes",
                    "Valor total: maior para menor",
                    "Valor total: menor para maior",
                    "Saldo restante: maior para menor",
                    "Saldo restante: menor para maior",
                    "Vencimento: mais próximo",
                    "Vencimento: mais distante",
                ),
                state="readonly",
                width=34,
                font=("Segoe UI", 9),
            ).pack(side="left")

        table_frame = tk.Frame(wrapper, bg=CARD)
        table_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                            selectmode="browse")
        for column, width in zip(columns, widths):
            tree.heading(column, text=column)
            tree.column(column, width=width, minwidth=55,
                        anchor="w" if column == "Descrição" else "center",
                        stretch=column == "Descrição")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        tree.tag_configure("alternate", background="#F8FAFD")
        return tree

    def add_installment(self):
        try:
            description = self.installment_fields["description"].get().strip()
            if not description:
                raise ValueError("Informe a descrição da conta.")
            installment_amount = round(
                parse_currency(self.installment_fields["value"].get()), 2
            )
            try:
                count = int(self.installment_fields["count"].get())
            except ValueError as error:
                raise ValueError("Informe o total de parcelas como um número inteiro.") from error
            try:
                paid = int(self.installment_fields["paid"].get())
            except ValueError as error:
                raise ValueError("Informe as parcelas pagas como um número inteiro.") from error
            due_date = parse_date(self.installment_fields["due"].get())
            if count < 1:
                raise ValueError("O total de parcelas deve ser pelo menos 1.")
            if paid < 0 or paid > count:
                raise ValueError("Parcelas pagas deve estar entre 0 e o total.")
            amount = round(installment_amount * count, 2)
        except ValueError as error:
            messagebox.showwarning("Confira os dados", str(error), parent=self.root)
            return

        try:
            cursor.execute(
                """INSERT INTO parcelas
                   (descricao, valor_total, total_parcelas, parcelas_pagas,
                    vencimento, valor_pago, valor_parcela)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    description,
                    amount,
                    count,
                    paid,
                    due_date.strftime("%d/%m/%Y"),
                    round(installment_amount * paid, 2),
                    installment_amount,
                ),
            )
            conn.commit()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao salvar", str(error), parent=self.root)
            return

        for key in ("description", "value", "count", "paid"):
            self.installment_fields[key].set("")
        self.installment_fields["due"].set(date.today().strftime("%d/%m/%Y"))
        self.refresh_all()
        messagebox.showinfo("Conta adicionada", "A conta foi cadastrada com sucesso.",
                            parent=self.root)

    def add_expense(self):
        try:
            description = self.expense_fields["description"].get().strip()
            if not description:
                raise ValueError("Informe a descrição do gasto.")
            amount = parse_currency(self.expense_fields["value"].get())
            expense_date = parse_date(self.expense_fields["date"].get())
        except ValueError as error:
            messagebox.showwarning("Confira os dados", str(error), parent=self.root)
            return

        try:
            cursor.execute(
                """INSERT INTO gastos_aleatorios (descricao, valor, data)
                   VALUES (?, ?, ?)""",
                (description, amount, expense_date.strftime("%d/%m/%Y")),
            )
            conn.commit()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao salvar", str(error), parent=self.root)
            return

        self.expense_fields["description"].set("")
        self.expense_fields["value"].set("")
        self.expense_fields["date"].set(date.today().strftime("%d/%m/%Y"))
        self.refresh_all()
        messagebox.showinfo("Gasto registrado", "O gasto foi salvo com sucesso.",
                            parent=self.root)

    def add_income(self):
        try:
            description = self.income_fields["description"].get().strip()
            if not description:
                raise ValueError("Informe a descrição do recebimento.")
            amount = parse_currency(self.income_fields["value"].get())
            income_date = parse_date(self.income_fields["date"].get())
        except ValueError as error:
            messagebox.showwarning("Confira os dados", str(error), parent=self.root)
            return

        try:
            cursor.execute(
                """INSERT INTO receitas (descricao, valor, data)
                   VALUES (?, ?, ?)""",
                (description, amount, income_date.strftime("%d/%m/%Y")),
            )
            conn.commit()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao salvar", str(error), parent=self.root)
            return

        self.income_fields["description"].set("")
        self.income_fields["value"].set("")
        self.income_fields["date"].set(date.today().strftime("%d/%m/%Y"))
        self.refresh_all()
        messagebox.showinfo(
            "Recebimento registrado",
            "O valor recebido foi salvo com sucesso.",
            parent=self.root,
        )

    def _get_totals(self):
        cursor.execute("SELECT COALESCE(SUM(valor_total), 0) FROM parcelas")
        installment_total = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(valor_pago), 0) FROM parcelas")
        paid_total = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(valor), 0) FROM gastos_aleatorios")
        expense_total = cursor.fetchone()[0]
        return installment_total, paid_total, expense_total

    def refresh_all(self):
        self.refresh_installments()
        self.refresh_expenses()
        self.refresh_income()
        self.refresh_investment_contributions()
        self.refresh_dashboard()
        self.refresh_savings()

    def refresh_installments(self):
        if not hasattr(self, "installment_tree"):
            return
        for item in self.installment_tree.get_children():
            self.installment_tree.delete(item)
        search = self.installment_search.get().strip().casefold()
        try:
            cursor.execute("SELECT * FROM parcelas ORDER BY id DESC")
            rows = cursor.fetchall()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao carregar contas", str(error), parent=self.root)
            return
        filtered_rows = [
            row for row in rows
            if not search or search in " ".join(map(str, row)).casefold()
        ]
        sort_option = self.installment_sort.get()
        if sort_option == "Valor total: maior para menor":
            filtered_rows.sort(key=lambda row: (row[2], row[0]), reverse=True)
        elif sort_option == "Valor total: menor para maior":
            filtered_rows.sort(key=lambda row: (row[2], -row[0]))
        elif sort_option == "Saldo restante: maior para menor":
            filtered_rows.sort(
                key=lambda row: (max(row[2] - row[6], 0), row[0]),
                reverse=True,
            )
        elif sort_option == "Saldo restante: menor para maior":
            filtered_rows.sort(
                key=lambda row: (max(row[2] - row[6], 0), -row[0])
            )
        elif sort_option == "Vencimento: mais próximo":
            filtered_rows.sort(
                key=lambda row: (
                    parse_date(row[5]) if row[5] else date.max,
                    -row[0],
                )
            )
        elif sort_option == "Vencimento: mais distante":
            filtered_rows.sort(
                key=lambda row: (
                    parse_date(row[5]) if row[5] else date.min,
                    row[0],
                ),
                reverse=True,
            )
        for index, row in enumerate(filtered_rows):
            self.installment_tree.insert(
                "", "end", iid=str(row[0]),
                values=(
                    row[0],
                    row[1],
                    format_currency(row[7]),
                    format_currency(row[2]),
                    format_currency(row[6]),
                    format_currency(max(row[2] - row[6], 0)),
                    row[3],
                    row[4],
                    row[3] - row[4],
                    row[5],
                ),
                tags=("alternate",) if index % 2 else (),
            )

    def refresh_income(self):
        if not hasattr(self, "income_tree"):
            return
        for item in self.income_tree.get_children():
            self.income_tree.delete(item)
        search = self.income_search.get().strip().casefold()
        try:
            cursor.execute("SELECT * FROM receitas ORDER BY id DESC")
            rows = cursor.fetchall()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Erro ao carregar recebimentos", str(error), parent=self.root
            )
            return
        current_month_total = 0.0
        for index, row in enumerate(rows):
            try:
                recorded = parse_date(row[3])
            except ValueError:
                recorded = None
            if recorded and (recorded.year, recorded.month) == (
                date.today().year,
                date.today().month,
            ):
                current_month_total += row[2]
            if search and search not in " ".join(map(str, row)).casefold():
                continue
            self.income_tree.insert(
                "", "end", iid=str(row[0]),
                values=(row[0], row[1], format_currency(row[2]), row[3]),
                tags=("alternate",) if index % 2 else (),
            )
        self.current_month_income.configure(text=format_currency(current_month_total))

    def add_investment_contribution(self):
        try:
            description = self.investment_fields["description"].get().strip()
            if not description:
                raise ValueError("Informe o nome do investimento.")
            amount = round(
                parse_currency(self.investment_fields["value"].get()), 2
            )
            contribution_date = parse_date(self.investment_fields["date"].get())
        except ValueError as error:
            messagebox.showwarning("Confira os dados", str(error), parent=self.root)
            return

        try:
            cursor.execute(
                """INSERT INTO investimentos_aportes (descricao, valor, data)
                   VALUES (?, ?, ?)""",
                (description, amount, contribution_date.strftime("%d/%m/%Y")),
            )
            conn.commit()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao registrar aporte", str(error), parent=self.root)
            return

        self.investment_fields["description"].set("")
        self.investment_fields["value"].set("")
        self.investment_fields["date"].set(date.today().strftime("%d/%m/%Y"))
        self.refresh_all()
        messagebox.showinfo(
            "Aporte registrado", "O aporte foi salvo com sucesso.", parent=self.root
        )

    def update_investment_balance(self):
        try:
            balance = round(
                parse_currency(self.investment_balance_value.get(), allow_zero=True), 2
            )
            balance_date = parse_date(self.investment_balance_date.get())
        except ValueError as error:
            messagebox.showwarning("Confira os dados", str(error), parent=self.root)
            return

        try:
            cursor.execute(
                """INSERT INTO investimentos_saldos (valor, data)
                   VALUES (?, ?)""",
                (balance, balance_date.strftime("%d/%m/%Y")),
            )
            conn.commit()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Erro ao atualizar saldo", str(error), parent=self.root
            )
            return

        self.investment_balance_value.set("")
        self.investment_balance_date.set(date.today().strftime("%d/%m/%Y"))
        self.refresh_all()
        messagebox.showinfo(
            "Saldo atualizado",
            "O saldo da carteira foi registrado para acompanhar sua evolução.",
            parent=self.root,
        )

    def refresh_investment_contributions(self):
        if not hasattr(self, "investment_tree"):
            return
        for item in self.investment_tree.get_children():
            self.investment_tree.delete(item)
        search = self.investment_search.get().strip().casefold()
        try:
            cursor.execute(
                "SELECT id, descricao, valor, data "
                "FROM investimentos_aportes ORDER BY id DESC"
            )
            contributions = cursor.fetchall()
            cursor.execute(
                "SELECT id, valor, data FROM investimentos_saldos ORDER BY id DESC"
            )
            balances = cursor.fetchall()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Erro ao carregar histórico de investimentos",
                str(error),
                parent=self.root,
            )
            return
        rows = []
        for record_id, description, amount, recorded in contributions:
            try:
                sort_date = parse_date(recorded)
            except ValueError:
                sort_date = date.min
            rows.append((
                f"aporte:{record_id}", record_id, "Aporte", description,
                amount, recorded, sort_date,
            ))
        for record_id, amount, recorded in balances:
            try:
                sort_date = parse_date(recorded)
            except ValueError:
                sort_date = date.min
            rows.append((
                f"saldo:{record_id}", record_id, "Saldo", "Saldo da carteira",
                amount, recorded, sort_date,
            ))
        rows.sort(key=lambda row: (row[6], row[1]), reverse=True)
        for index, row in enumerate(rows):
            if search and search not in " ".join(map(str, row)).casefold():
                continue
            self.investment_tree.insert(
                "", "end", iid=row[0],
                values=(
                    row[1], row[2], row[3], format_currency(row[4]), row[5]
                ),
                tags=("alternate",) if index % 2 else (),
            )

    def edit_selected_investment(self):
        selection = self.investment_tree.selection()
        if not selection:
            messagebox.showinfo(
                "Selecione um registro",
                "Escolha um aporte ou saldo no histórico para editar.",
                parent=self.root,
            )
            return

        record_type, record_id = selection[0].split(":", 1)
        try:
            if record_type == "aporte":
                cursor.execute(
                    "SELECT descricao, valor, data FROM investimentos_aportes "
                    "WHERE id = ?",
                    (record_id,),
                )
            else:
                cursor.execute(
                    "SELECT valor, data FROM investimentos_saldos WHERE id = ?",
                    (record_id,),
                )
            record = cursor.fetchone()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Erro ao carregar registro", str(error), parent=self.root
            )
            return
        if record is None:
            messagebox.showerror(
                "Registro não encontrado",
                "Atualize o histórico e tente novamente.",
                parent=self.root,
            )
            return

        is_contribution = record_type == "aporte"
        dialog = tk.Toplevel(self.root)
        dialog.title("Editar aporte" if is_contribution else "Editar saldo")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        body = self._card(dialog, padx=20, pady=18)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(
            body,
            text="Editar aporte" if is_contribution else "Editar saldo informado",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        description_var = tk.StringVar(value=record[0] if is_contribution else "")
        if is_contribution:
            tk.Label(body, text="Investimento", bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
            ttk.Entry(body, textvariable=description_var, width=38).pack(
                fill="x", ipady=5, pady=(0, 10)
            )

        amount_var = tk.StringVar(value=str(record[1] if is_contribution else record[0]))
        date_var = tk.StringVar(value=record[2] if is_contribution else record[1])
        tk.Label(body, text="Valor (R$)", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Entry(body, textvariable=amount_var, width=38).pack(
            fill="x", ipady=5, pady=(0, 10)
        )
        tk.Label(body, text="Data (dd/mm/aaaa)", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Entry(body, textvariable=date_var, width=38).pack(
            fill="x", ipady=5, pady=(0, 14)
        )

        def save_changes():
            try:
                description = description_var.get().strip()
                if is_contribution and not description:
                    raise ValueError("Informe o nome do investimento.")
                amount = round(
                    parse_currency(amount_var.get(), allow_zero=not is_contribution),
                    2,
                )
                recorded_date = parse_date(date_var.get()).strftime("%d/%m/%Y")
            except ValueError as error:
                messagebox.showwarning(
                    "Confira os dados", str(error), parent=dialog
                )
                return

            try:
                if is_contribution:
                    cursor.execute(
                        """UPDATE investimentos_aportes
                           SET descricao = ?, valor = ?, data = ? WHERE id = ?""",
                        (description, amount, recorded_date, record_id),
                    )
                else:
                    cursor.execute(
                        """UPDATE investimentos_saldos
                           SET valor = ?, data = ? WHERE id = ?""",
                        (amount, recorded_date, record_id),
                    )
                if cursor.rowcount != 1:
                    raise sqlite3.Error("O registro não foi encontrado para atualização.")
                conn.commit()
            except sqlite3.Error as error:
                conn.rollback()
                messagebox.showerror(
                    "Erro ao editar registro", str(error), parent=dialog
                )
                return
            dialog.destroy()
            self.refresh_all()
            messagebox.showinfo(
                "Registro atualizado",
                "As alterações foram salvas com sucesso.",
                parent=self.root,
            )

        tk.Button(
            body, text="Salvar alterações", command=save_changes,
            bg=ACCENT, fg="white", activebackground="#3D68E7",
            activeforeground="white", relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9, "bold"), padx=14, pady=8,
        ).pack(anchor="e")

    def _edit_investment_from_double_click(self, event):
        row_id = self.investment_tree.identify_row(event.y)
        if row_id:
            self.investment_tree.selection_set(row_id)
            self.edit_selected_investment()

    def refresh_savings(self):
        if not hasattr(self, "savings_tree"):
            return
        for item in self.savings_tree.get_children():
            self.savings_tree.delete(item)
        try:
            cursor.execute(
                "SELECT id, valor, data FROM investimentos_aportes ORDER BY id"
            )
            contributions = cursor.fetchall()
            cursor.execute(
                "SELECT id, valor, data FROM investimentos_saldos ORDER BY id"
            )
            balance_updates = cursor.fetchall()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Erro ao calcular evolução dos investimentos",
                str(error),
                parent=self.root,
            )
            return

        today = date.today()
        months = []
        year, month = today.year, today.month
        for _ in range(12):
            months.append((year, month))
            month -= 1
            if month == 0:
                year -= 1
                month = 12
        parsed_contributions = []
        for record_id, amount, date_text in contributions:
            try:
                parsed_contributions.append(
                    (parse_date(date_text), record_id, amount)
                )
            except ValueError:
                continue
        parsed_balances = []
        for record_id, amount, date_text in balance_updates:
            try:
                parsed_balances.append((parse_date(date_text), record_id, amount))
            except ValueError:
                continue

        total_contributed = sum(
            amount for recorded, _, amount in parsed_contributions if recorded <= today
        )
        current_balance = max(
            (
                (recorded, record_id, amount)
                for recorded, record_id, amount in parsed_balances
                if recorded <= today
            ),
            default=None,
        )
        self.investment_summary["contributed"].configure(
            text=format_currency(total_contributed)
        )
        if current_balance is None:
            self.investment_summary["balance"].configure(text="Não informado")
            self.investment_summary["change"].configure(text="—", fg=GREEN)
            self.investment_balance_updated.configure(
                text="Saldo ainda não informado"
            )
        else:
            contributed_at_balance_date = sum(
                amount for recorded, _, amount in parsed_contributions
                if recorded <= current_balance[0]
            )
            current_change = current_balance[2] - contributed_at_balance_date
            self.investment_summary["balance"].configure(
                text=format_currency(current_balance[2])
            )
            self.investment_balance_updated.configure(
                text=f"Saldo informado em {current_balance[0].strftime('%d/%m/%Y')}"
            )
            self.investment_summary["change"].configure(
                text=format_currency(current_change),
                fg=GREEN if current_change >= 0 else RED,
            )
        month_names = (
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
        )
        for index, key in enumerate(months):
            last_day = date(key[0], key[1], calendar.monthrange(*key)[1])
            as_of = min(last_day, today)
            month_contributions = sum(
                amount for recorded, _, amount in parsed_contributions
                if (recorded.year, recorded.month) == key and recorded <= today
            )
            cumulative_contributions = sum(
                amount for recorded, _, amount in parsed_contributions
                if recorded <= as_of
            )
            month_balance = max(
                (
                    (recorded, record_id, amount)
                    for recorded, record_id, amount in parsed_balances
                    if recorded <= as_of
                ),
                default=None,
            )
            balance_text = (
                format_currency(month_balance[2]) if month_balance else "—"
            )
            change_text = (
                format_currency(month_balance[2] - cumulative_contributions)
                if month_balance else "—"
            )
            self.savings_tree.insert(
                "", "end",
                values=(
                    f"{month_names[key[1] - 1].capitalize()} {key[0]}",
                    format_currency(month_contributions),
                    format_currency(cumulative_contributions),
                    balance_text,
                    change_text,
                ),
                tags=("alternate",) if index % 2 else (),
            )

    def refresh_expenses(self):
        if not hasattr(self, "expense_tree"):
            return
        for item in self.expense_tree.get_children():
            self.expense_tree.delete(item)
        search = self.expense_search.get().strip().casefold()
        try:
            cursor.execute("SELECT * FROM gastos_aleatorios ORDER BY id DESC")
            rows = cursor.fetchall()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao carregar gastos", str(error), parent=self.root)
            return
        for index, row in enumerate(rows):
            if search and search not in " ".join(map(str, row)).casefold():
                continue
            self.expense_tree.insert(
                "", "end", iid=str(row[0]),
                values=(row[0], row[1], format_currency(row[2]), row[3]),
                tags=("alternate",) if index % 2 else (),
            )

    def refresh_dashboard(self):
        if not hasattr(self, "summary_values"):
            return
        try:
            installment_total, paid_total, expense_total = self._get_totals()
            cursor.execute(
                """SELECT descricao, vencimento, valor_total, valor_pago
                   FROM parcelas ORDER BY id DESC"""
            )
            installments = cursor.fetchall()
            cursor.execute("SELECT data, valor FROM gastos_aleatorios")
            expenses = cursor.fetchall()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao atualizar painel", str(error), parent=self.root)
            return

        self.summary_values["installments"].configure(
            text=format_currency(installment_total)
        )
        self.summary_values["paid"].configure(text=format_currency(paid_total))
        self.summary_values["remaining"].configure(
            text=format_currency(max(installment_total - paid_total, 0))
        )
        self.summary_values["expenses"].configure(text=format_currency(expense_total))

        self._populate_alerts(installments)
        self.monthly_expenses = expenses
        self._draw_chart()

    def _populate_alerts(self, installments):
        for widget in self.alert_list.winfo_children():
            widget.destroy()
        upcoming = []
        today = date.today()
        for description, due_text, total_amount, paid_amount in installments:
            if total_amount - paid_amount <= 0:
                continue
            try:
                due_date = parse_date(due_text)
            except ValueError:
                continue
            days = (due_date - today).days
            if 0 <= days <= 5:
                upcoming.append((due_date, description, days))

        if not upcoming:
            tk.Label(
                self.alert_list,
                text="✓  Nenhuma conta vencendo nos próximos 5 dias",
                bg="#F0FAF6",
                fg="#288568",
                anchor="w",
                padx=12,
                pady=12,
                font=("Segoe UI", 9),
            ).pack(fill="x", pady=4)
            return

        for due_date, description, days in sorted(upcoming):
            line = tk.Frame(self.alert_list, bg="#FFF8F1", padx=12, pady=10)
            line.pack(fill="x", pady=4)
            tk.Label(line, text="!", bg="#FFF0DD", fg="#C77821",
                     width=2, font=("Segoe UI", 9, "bold")).pack(side="left")
            detail = tk.Frame(line, bg="#FFF8F1")
            detail.pack(side="left", fill="x", expand=True, padx=9)
            tk.Label(detail, text=description, bg="#FFF8F1", fg=TEXT,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
            tk.Label(detail, text=due_date.strftime("%d/%m/%Y"), bg="#FFF8F1",
                     fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))
            when = "Hoje" if days == 0 else "Amanhã" if days == 1 else f"Em {days} dias"
            tk.Label(line, text=when, bg="#FFF8F1", fg="#C77821",
                     font=("Segoe UI", 8, "bold")).pack(side="right")

    def _draw_chart(self):
        if not hasattr(self, "chart") or not hasattr(self, "monthly_expenses"):
            return
        canvas = self.chart
        canvas.delete("all")
        width = max(canvas.winfo_width(), 320)
        height = max(canvas.winfo_height(), 220)
        today = date.today()
        months = []
        year, month = today.year, today.month
        for _ in range(5, -1, -1):
            months.append((year, month))
            month -= 1
            if month == 0:
                year -= 1
                month = 12

        totals = {key: 0.0 for key in months}
        for text, value in self.monthly_expenses:
            try:
                recorded = parse_date(text)
            except ValueError:
                continue
            key = (recorded.year, recorded.month)
            if key in totals:
                totals[key] += value

        left, right, top, bottom = 44, width - 14, 18, height - 34
        chart_height = max(bottom - top, 80)
        max_value = max(totals.values(), default=0)
        max_value = max(max_value, 1)
        for step in range(4):
            y = top + chart_height * step / 3
            canvas.create_line(left, y, right, y, fill="#EEF1F6")
            label = format_currency(max_value * (3 - step) / 3)
            canvas.create_text(left - 7, y, text=label, anchor="e",
                               fill="#98A3B3", font=("Segoe UI", 7))

        slot = (right - left) / len(months)
        for index, key in enumerate(months):
            x_center = left + slot * (index + 0.5)
            bar_height = chart_height * totals[key] / max_value
            bar_width = min(34, slot * 0.48)
            canvas.create_rectangle(
                x_center - bar_width / 2,
                bottom - bar_height,
                x_center + bar_width / 2,
                bottom,
                fill=ACCENT if key == months[-1] else "#AFC3FF",
                outline="",
            )
            label = calendar.month_abbr[key[1]].capitalize()
            canvas.create_text(x_center, bottom + 16, text=label, fill=MUTED,
                               font=("Segoe UI", 8))
            if totals[key]:
                canvas.create_text(
                    x_center, bottom - bar_height - 10,
                    text=format_currency(totals[key]), fill=TEXT,
                    font=("Segoe UI", 7),
                )

    def delete_selected(self, table_title):
        if table_title == "Contas cadastradas":
            tree, table_name, label = self.installment_tree, "parcelas", "esta conta"
        elif table_title == "Histórico de gastos":
            tree, table_name, label = self.expense_tree, "gastos_aleatorios", "este gasto"
        elif table_title == "Histórico de investimentos":
            tree, table_name, label = (
                self.investment_tree, None, "este registro de investimento"
            )
        else:
            tree, table_name, label = self.income_tree, "receitas", "este recebimento"
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Selecione um registro",
                                "Escolha uma linha da tabela para excluir.",
                                parent=self.root)
            return
        if not messagebox.askyesno(
            "Confirmar exclusão",
            f"Tem certeza de que deseja excluir {label}? Esta ação não pode ser desfeita.",
            parent=self.root,
        ):
            return
        try:
            if table_name is None:
                record_type, record_id = selection[0].split(":", 1)
                investment_table = (
                    "investimentos_aportes" if record_type == "aporte"
                    else "investimentos_saldos"
                )
                cursor.execute(
                    f"DELETE FROM {investment_table} WHERE id = ?", (record_id,)
                )
            else:
                cursor.execute(
                    f"DELETE FROM {table_name} WHERE id = ?", (selection[0],)
                )
            conn.commit()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao excluir", str(error), parent=self.root)
            return
        self.refresh_all()

    def _edit_due_date_from_cell(self, event):
        if self.installment_tree.identify_column(event.x) != "#9":
            return
        row_id = self.installment_tree.identify_row(event.y)
        if not row_id:
            return
        self.installment_tree.selection_set(row_id)
        self.edit_due_date()

    def edit_due_date(self):
        selection = self.installment_tree.selection()
        if not selection:
            messagebox.showinfo(
                "Selecione uma conta",
                "Selecione uma conta ou dê duplo clique no vencimento que deseja alterar.",
                parent=self.root,
            )
            return

        try:
            cursor.execute(
                "SELECT vencimento FROM parcelas WHERE id = ?",
                (selection[0],),
            )
            row = cursor.fetchone()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao carregar vencimento", str(error),
                                 parent=self.root)
            return
        if row is None:
            messagebox.showerror(
                "Conta não encontrada",
                "Atualize a lista e tente novamente.",
                parent=self.root,
            )
            return

        new_date = simpledialog.askstring(
            "Alterar vencimento",
            "Informe a nova data de vencimento (dd/mm/aaaa):",
            initialvalue=row[0],
            parent=self.root,
        )
        if new_date is None:
            return
        try:
            normalized_date = parse_date(new_date).strftime("%d/%m/%Y")
        except ValueError as error:
            messagebox.showwarning("Confira a data", str(error), parent=self.root)
            return

        try:
            cursor.execute(
                "UPDATE parcelas SET vencimento = ? WHERE id = ?",
                (normalized_date, selection[0]),
            )
            conn.commit()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao alterar vencimento", str(error),
                                 parent=self.root)
            return
        self.refresh_all()
        messagebox.showinfo(
            "Vencimento alterado",
            f"A data foi atualizada para {normalized_date}.",
            parent=self.root,
        )

    def register_payment(self):
        selection = self.installment_tree.selection()
        if not selection:
            messagebox.showinfo(
                "Selecione uma conta",
                "Escolha uma conta parcelada para registrar o pagamento.",
                parent=self.root,
            )
            return

        try:
            cursor.execute(
                """SELECT valor_total, total_parcelas, valor_pago, vencimento,
                          valor_parcela
                   FROM parcelas WHERE id = ?""",
                (selection[0],),
            )
            account = cursor.fetchone()
        except sqlite3.Error as error:
            messagebox.showerror("Erro ao carregar conta", str(error), parent=self.root)
            return
        if account is None:
            messagebox.showerror(
                "Conta não encontrada",
                "Atualize a lista e tente novamente.",
                parent=self.root,
            )
            return

        total, total_installments, paid_amount, due_date, installment_amount = account
        if total_installments <= 0:
            messagebox.showerror(
                "Dados inválidos",
                "Esta conta está cadastrada sem parcelas válidas.",
                parent=self.root,
            )
            return
        remaining = round(max(total - paid_amount, 0), 2)
        if remaining <= 0:
            messagebox.showinfo(
                "Conta quitada",
                "Esta conta já está totalmente paga.",
                parent=self.root,
            )
            return
        suggested = min(installment_amount, remaining)
        amount_text = simpledialog.askstring(
            "Registrar pagamento",
            f"Quanto foi pago? Falta pagar {format_currency(remaining)}.",
            initialvalue=format_currency(suggested),
            parent=self.root,
        )
        if amount_text is None:
            return
        try:
            amount = round(parse_currency(amount_text), 2)
            if amount > remaining:
                raise ValueError(
                    f"O pagamento não pode ultrapassar o saldo de "
                    f"{format_currency(remaining)}."
                )
        except ValueError as error:
            messagebox.showwarning("Confira o valor", str(error), parent=self.root)
            return

        payment_date_text = simpledialog.askstring(
            "Data do pagamento",
            "Informe a data em que o pagamento foi realizado (dd/mm/aaaa):",
            initialvalue=date.today().strftime("%d/%m/%Y"),
            parent=self.root,
        )
        if payment_date_text is None:
            return
        try:
            payment_date = parse_date(payment_date_text).strftime("%d/%m/%Y")
        except ValueError as error:
            messagebox.showwarning("Confira a data", str(error), parent=self.root)
            return

        updated_due_date = due_date
        change_due_date = messagebox.askyesno(
            "Atualizar vencimento",
            "Deseja alterar o vencimento desta conta para a próxima parcela?",
            parent=self.root,
        )
        if change_due_date:
            due_date_text = simpledialog.askstring(
                "Novo vencimento",
                "Informe a nova data de vencimento (dd/mm/aaaa):",
                initialvalue=due_date,
                parent=self.root,
            )
            if due_date_text is None:
                return
            try:
                updated_due_date = parse_date(due_date_text).strftime("%d/%m/%Y")
            except ValueError as error:
                messagebox.showwarning("Confira a data", str(error), parent=self.root)
                return

        updated_paid = round(paid_amount + amount, 2)
        updated_installments = paid_installment_count(
            updated_paid, installment_amount, total_installments
        )
        try:
            cursor.execute(
                """UPDATE parcelas
                   SET valor_pago = ?, parcelas_pagas = ?, vencimento = ?
                   WHERE id = ?""",
                (updated_paid, updated_installments, updated_due_date, selection[0]),
            )
            cursor.execute(
                """INSERT INTO pagamentos_parcelas (parcela_id, valor, data)
                   VALUES (?, ?, ?)""",
                (selection[0], amount, payment_date),
            )
            conn.commit()
        except sqlite3.Error as error:
            conn.rollback()
            messagebox.showerror("Erro ao registrar pagamento", str(error),
                                 parent=self.root)
            return
        self.refresh_all()
        messagebox.showinfo(
            "Pagamento registrado",
            f"Pago até agora: {format_currency(updated_paid)}\n"
            f"Falta pagar: {format_currency(round(total - updated_paid, 2))}\n"
            f"Valor fixo da parcela: {format_currency(installment_amount)}\n"
            f"Próximo vencimento: {updated_due_date}",
            parent=self.root,
        )

    def export_table(self, table_title):
        if table_title == "Contas cadastradas":
            query = """SELECT id, descricao, valor_parcela, valor_total, valor_pago,
                              ROUND(MAX(valor_total - valor_pago, 0), 2),
                              total_parcelas, parcelas_pagas, vencimento
                       FROM parcelas ORDER BY id DESC"""
            headers = (
                "ID", "Descrição", "Valor fixo da parcela", "Valor total",
                "Valor pago", "Falta pagar", "Total de parcelas",
                "Parcelas pagas", "Vencimento",
            )
            filename = "contas_parceladas.csv"
        elif table_title == "Histórico de gastos":
            query = "SELECT id, descricao, valor, data FROM gastos_aleatorios ORDER BY id DESC"
            headers = ("ID", "Descrição", "Valor", "Data")
            filename = "gastos_avulsos.csv"
        elif table_title == "Histórico de investimentos":
            query = """
                SELECT id, tipo, descricao, valor, data FROM (
                    SELECT id, 'Aporte' AS tipo, descricao, valor, data
                    FROM investimentos_aportes
                    UNION ALL
                    SELECT id, 'Saldo' AS tipo, 'Saldo da carteira' AS descricao,
                           valor, data
                    FROM investimentos_saldos
                )
                ORDER BY data DESC, id DESC
            """
            headers = ("ID", "Tipo", "Descrição", "Valor", "Data")
            filename = "historico_investimentos.csv"
        else:
            query = "SELECT id, descricao, valor, data FROM receitas ORDER BY id DESC"
            headers = ("ID", "Descrição", "Valor recebido", "Data")
            filename = "recebimentos.csv"
        destination = filedialog.asksaveasfilename(
            parent=self.root,
            title="Exportar dados",
            defaultextension=".csv",
            initialfile=filename,
            filetypes=(("Arquivo CSV", "*.csv"),),
        )
        if not destination:
            return
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            with open(destination, "w", newline="", encoding="utf-8-sig") as output:
                writer = csv.writer(output, delimiter=";")
                writer.writerow(headers)
                writer.writerows(rows)
        except (OSError, sqlite3.Error) as error:
            messagebox.showerror("Erro ao exportar", str(error), parent=self.root)
            return
        messagebox.showinfo("Exportação concluída",
                            f"Arquivo salvo em:\n{destination}", parent=self.root)

    def close(self):
        conn.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = FinanceApp(root)
    root.mainloop()
