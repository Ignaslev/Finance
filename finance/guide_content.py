def image(lang, filename, alt, caption="", variant=""):
    return {
        "type": "image",
        "src": f"img/guide/{lang}/{filename}",
        "alt": alt,
        "caption": caption,
        "variant": variant,
    }


GUIDE_CONTENT = {
    "en": [
        {
            "id": "introduction",
            "title": "Introduction",
            "subtitle": "From zero to financial clarity",
            "body": [
                image(
                    "en",
                    "mascot.png",
                    "Money Compass mascot",
                    "Money Compass — personal finance tracker.",
                    variant="mascot",
                ),
                {
                    "type": "paragraph",
                    "text": "Money Compass is a web app for tracking personal finances. You export bank statements from your bank and import them into Money Compass — no direct bank connection is required.",
                },
                {
                    "type": "paragraph",
                    "text": "You can track spending by category, monitor net worth, use AI categorization, view charts, manage investments, and receive AI-generated financial reports.",
                },
                {
                    "type": "note",
                    "text": "Money Compass does not connect to your bank directly. You stay in control by exporting and uploading your own statement files.",
                },
            ],
        },
        {
            "id": "app-overview",
            "title": "App Overview",
            "subtitle": "Main areas of Money Compass",
            "body": [
                image(
                    "en",
                    "desktop-nav.png",
                    "Desktop navigation example",
                    "Desktop navigation.",
                ),
                image(
                    "en",
                    "mobile-nav.png",
                    "Mobile navigation example",
                    "Mobile navigation.",
                ),
                {
                    "type": "table",
                    "headers": ["Section", "What you do here"],
                    "rows": [
                        ["Dashboard", "View total net worth, income vs spending, category breakdown, savings goals, and monthly net balance."],
                        ["Statistics", "Review all-time totals, income sources, subscriptions, merchants, and categorization coverage."],
                        ["Reports", "Read AI-generated monthly and weekly financial summaries."],
                        ["Portfolio", "Track crypto and stock / ETF holdings with live prices and total value."],
                        ["Transactions", "Upload bank statements, browse, filter, categorize, hide, and restore transactions."],
                        ["Profile / Settings", "Manage accounts, categories, savings goals, language preference, and data deletion."],
                    ],
                },
                {
                    "type": "note",
                    "text": "On mobile, use the bottom navigation bar: Home, Invest, Statistics, Txns, and Menu. On desktop, use the top navigation bar.",
                },
                {
                    "type": "heading",
                    "text": "What Money Compass is not",
                },
                {
                    "type": "list",
                    "items": [
                        "It does not connect to your bank directly.",
                        "It does not have a dedicated mobile app, but the website is mobile-friendly.",
                        "It does not provide a public API.",
                        "Account balances are calculated from imported transactions after you set an initial balance anchor.",
                    ],
                },
            ],
        },
        {
            "id": "getting-started",
            "title": "Getting Started",
            "subtitle": "Register, set up accounts, and complete onboarding",
            "body": [
                {
                    "type": "heading",
                    "text": "Register and log in",
                },
                {
                    "type": "list",
                    "items": [
                        "Go to the app URL and click Register.",
                        "Enter your details and create your account.",
                        "On future visits, click Login and enter your username and password.",
                        "To log out, click the avatar or initials in the top-right corner and choose Log Out.",
                    ],
                },
                {
                    "type": "heading",
                    "text": "Onboarding — 5 steps",
                },
                {
                    "type": "table",
                    "headers": ["Step", "What to do"],
                    "rows": [
                        ["1. Categories", "Review the default categories. Add the ones you need and remove the ones you do not use."],
                        ["2. Upload", "Upload your first CSV or XLSX bank statement."],
                        ["3. Set Balance", "Go to Profile and set the current balance for each financial account."],
                        ["4. Teach AI", "Manually assign categories to at least 30 transactions so the AI can learn your spending habits."],
                        ["5. Ready", "AI auto-categorization becomes active after onboarding is complete."],
                    ],
                },
                {
                    "type": "note",
                    "text": "AI auto-categorization activates only after you manually categorize at least 30 transactions.",
                },
                {
                    "type": "heading",
                    "text": "Set up financial accounts",
                },
                image(
                    "en",
                    "accounts-setup.png",
                    "Financial accounts setup example",
                    "Financial accounts setup in Profile.",
                ),
                {
                    "type": "list",
                    "items": [
                        "Open Profile from the avatar menu, or on mobile open Menu → Settings.",
                        "Add each account you use, for example Revolut, SEB, Cash Wallet, Savings, or Investment.",
                        "Choose the correct type: Bank, Cash, Savings, or Investment.",
                        "After your first CSV upload, enter the current balance for each account and save it.",
                    ],
                },
            ],
        },
        {
            "id": "importing-transactions",
            "title": "Importing Transactions",
            "subtitle": "Upload bank statements safely",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Transactions are the core of Money Compass. You export a file from your bank and upload it into the app. Money Compass parses the file, skips duplicates, and adds new rows to your transaction history.",
                },
                {
                    "type": "heading",
                    "text": "Supported statement formats",
                },
                {
                    "type": "list",
                    "items": [
                        "SEB Bank",
                        "Swedbank",
                        "Revolut",
                        "Generic CSV or XLSX files with date, merchant, and amount columns",
                    ],
                },
                {
                    "type": "heading",
                    "text": "Upload process",
                },
                image(
                    "en",
                    "upload-statement.png",
                    "Upload statement form",
                    "Upload statement card.",
                ),
                {
                    "type": "list",
                    "items": [
                        "Open the Transactions page.",
                        "Choose the target account.",
                        "Choose the bank format.",
                        "Select the CSV or Excel file.",
                        "Click Upload and review the import summary.",
                    ],
                },
                {
                    "type": "note",
                    "text": "Re-uploading the same file is safe. Existing rows are detected as duplicates and skipped.",
                },
                {
                    "type": "heading",
                    "text": "Undo last upload",
                },
                {
                    "type": "paragraph",
                    "text": "If you uploaded the wrong file or selected the wrong account, use Undo last upload on the Transactions page. This permanently deletes transactions from the most recent import batch.",
                },
                {
                    "type": "heading",
                    "text": "Add a manual transaction",
                },
                {
                    "type": "paragraph",
                    "text": "For cash purchases or transactions that are not in a bank statement, use Add Manual on the Transactions page.",
                },
            ],
        },
        {
            "id": "transactions",
            "title": "Browsing & Managing Transactions",
            "subtitle": "Filter, categorize, hide, restore, and review transactions",
            "body": [
                {
                    "type": "heading",
                    "text": "Quick links",
                },
                {
                    "type": "table",
                    "headers": ["Link", "What it does"],
                    "rows": [
                        ["AI-categorized", "Shows transactions that AI has categorized."],
                        ["Low-confidence", "Shows AI suggestions that need your review."],
                        ["Uncategorized", "Shows transactions without a proper category."],
                        ["Deleted", "Shows soft-deleted transactions that can be restored."],
                    ],
                },
                {
                    "type": "heading",
                    "text": "Filtering",
                },
                image(
                    "en",
                    "filter-search.png",
                    "Transaction filter and search form",
                    "Filter and search transactions.",
                ),
                {
                    "type": "paragraph",
                    "text": "Use the Filter & Search card to filter by account, merchant search, date range, amount range, flow, and category.",
                },
                {
                    "type": "heading",
                    "text": "Assigning categories inline",
                },
                {
                    "type": "paragraph",
                    "text": "In the transaction table, change the Category dropdown on any row. A pending-change indicator appears, and a sticky Apply Changes bar lets you save all changes at once.",
                },
                {
                    "type": "heading",
                    "text": "Editing a transaction",
                },
                image(
                    "en",
                    "transaction-edit.png",
                    "Transaction edit page",
                    "Edit transaction details.",
                ),
                {
                    "type": "paragraph",
                    "text": "Click Edit on a transaction to change its category or add a user note. A category chosen manually by the user is protected and will not be overwritten by AI.",
                },
                {
                    "type": "heading",
                    "text": "Soft-deleting and restoring",
                },
                {
                    "type": "paragraph",
                    "text": "Soft-deleting hides a transaction from charts and lists without removing its fingerprint. This prevents the same row from being recreated if you upload the same bank file again.",
                },
                {
                    "type": "heading",
                    "text": "Refund detection",
                },
                image(
                    "en",
                    "refund-detection.png",
                    "Refund detection section",
                    "Found refunds section.",
                ),
                {
                    "type": "paragraph",
                    "text": "Money Compass detects potential refunds by matching one outgoing and one incoming transaction with the exact same amount, same currency, and a date difference of up to 10 days. You can delete both transactions from charts or ignore the suggestion.",
                },
            ],
        },
        {
            "id": "categories",
            "title": "Categories",
            "subtitle": "Understand where your money goes",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Categories let you label transactions so you can see exactly where your money is going.",
                },
                {
                    "type": "heading",
                    "text": "Creating categories",
                },
                image(
                    "en",
                    "categories.png",
                    "Categories management section",
                    "Category management.",
                ),
                {
                    "type": "paragraph",
                    "text": "Go to Profile, find the Categories section, enter a new category name, and click Add.",
                },
                {
                    "type": "list",
                    "items": [
                        "Food & Groceries",
                        "Dining Out",
                        "Transport",
                        "Rent / Bills",
                        "Subscriptions",
                        "Income",
                        "Health",
                        "Entertainment",
                        "Shopping",
                    ],
                },
                {
                    "type": "note",
                    "text": "The built-in Other category cannot be deleted. It is used as a fallback when a category is removed or when the AI is uncertain.",
                },
                {
                    "type": "heading",
                    "text": "Spending caps",
                },
                image(
                    "en",
                    "category-caps.png",
                    "Category spending caps section",
                    "Monthly category spending caps.",
                ),
                {
                    "type": "paragraph",
                    "text": "You can set a monthly spending cap for each category. When a cap is set, the Dashboard category chart shows a cap line.",
                },
                {
                    "type": "heading",
                    "text": "Deleting categories",
                },
                {
                    "type": "paragraph",
                    "text": "When a category is deleted, transactions using that category are reassigned to Other.",
                },
            ],
        },
        {
            "id": "ai-categorization",
            "title": "AI Categorization",
            "subtitle": "Automatic transaction categorization",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Money Compass uses AI to suggest categories for transactions. This helps reduce manual work after large imports.",
                },
                {
                    "type": "note",
                    "text": "AI categorization starts only after onboarding is complete and at least 30 transactions have been categorized manually.",
                },
                {
                    "type": "table",
                    "headers": ["Confidence", "Action"],
                    "rows": [
                        ["90% or higher", "Auto-applied."],
                        ["80%–89%", "Auto-applied as category."],
                        ["Below 80%", "Parked for manual review on the Low-confidence page."],
                        ["User-set category", "Never overwritten by AI."],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "The AI learns from your existing categorized transactions. The more accurately you categorize transactions manually, the better future suggestions become.",
                },
            ],
        },
        {
            "id": "dashboard",
            "title": "Dashboard",
            "subtitle": "Your financial summary at a glance",
            "body": [
                {
                    "type": "paragraph",
                    "text": "The Dashboard shows your total net worth, account composition, balance history, savings goals, income vs spending, monthly net balance, and spending by category.",
                },
                {
                    "type": "heading",
                    "text": "Total net worth",
                },
                image(
                    "en",
                    "dashboard-net-worth.png",
                    "Dashboard total net worth card",
                    "Total net worth.",
                ),
                {
                    "type": "paragraph",
                    "text": "Net worth is calculated from your account balance anchors and imported transactions. If the number drifts because of missing uploads, re-enter the correct balance in Profile.",
                },
                {
                    "type": "heading",
                    "text": "Accounts and assets",
                },
                image(
                    "en",
                    "accounts-assets.png",
                    "Accounts and assets table",
                    "Accounts and assets table.",
                ),
                {
                    "type": "heading",
                    "text": "Net worth history",
                },
                image(
                    "en",
                    "net-worth-history.png",
                    "Net worth history chart",
                    "Net worth history chart.",
                ),
                {
                    "type": "heading",
                    "text": "Savings goals",
                },
                image(
                    "en",
                    "savings-goals.png",
                    "Savings goals progress bars",
                    "Savings goals.",
                ),
                {
                    "type": "heading",
                    "text": "Income vs spending",
                },
                image(
                    "en",
                    "income-vs-spending.png",
                    "Income vs spending chart",
                    "Income vs spending chart.",
                ),
                {
                    "type": "heading",
                    "text": "Net by month",
                },
                image(
                    "en",
                    "net-by-month.png",
                    "Net by month table",
                    "Net by month.",
                ),
                {
                    "type": "heading",
                    "text": "Spending by category",
                },
                image(
                    "en",
                    "spending-per-category.png",
                    "Spending per category chart",
                    "Spending by category.",
                ),
                {
                    "type": "paragraph",
                    "text": "The spending chart lets you switch categories, change chart type, view monthly breakdowns, and open filtered transactions for a merchant in the selected month.",
                },
            ],
        },
        {
            "id": "statistics",
            "title": "Statistics",
            "subtitle": "Deeper financial analysis",
            "body": [
                {
                    "type": "paragraph",
                    "text": "The Statistics page shows all-time earned, all-time spent, lifetime net, average monthly income and spending, transaction count, categorization coverage, and merchant insights.",
                },
                {
                    "type": "heading",
                    "text": "Income sources",
                },
                {
                    "type": "paragraph",
                    "text": "Money Compass detects income sources from incoming transactions. You can review, track, untrack, or retrack income sources.",
                },
                {
                    "type": "heading",
                    "text": "Subscriptions",
                },
                {
                    "type": "paragraph",
                    "text": "Money Compass detects recurring outgoing payments as possible subscriptions. You can review candidates, confirm them, dismiss them, or retrack previously untracked subscriptions.",
                },
            ],
        },
        {
            "id": "reports",
            "title": "Reports",
            "subtitle": "AI-generated financial summaries",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Reports are AI-generated summaries of your finances written in plain language.",
                },
                {
                    "type": "heading",
                    "text": "Monthly reports",
                },
                {
                    "type": "paragraph",
                    "text": "Monthly reports are generated automatically after a month ends and include a written summary and key metrics.",
                },
                {
                    "type": "heading",
                    "text": "Weekly reports",
                },
                {
                    "type": "paragraph",
                    "text": "Weekly reports are generated automatically every Monday.",
                },
                {
                    "type": "heading",
                    "text": "Balance reconciliation",
                },
                {
                    "type": "paragraph",
                    "text": "The reconciliation table compares consecutive balance snapshots and checks whether imported transactions explain the difference between them.",
                },
            ],
        },
        {
            "id": "portfolio",
            "title": "Portfolio",
            "subtitle": "Track crypto and stock / ETF holdings",
            "body": [
                {
                    "type": "paragraph",
                    "text": "The Portfolio page lets you track cryptocurrency and stock / ETF holdings with current EUR prices and calculated total value.",
                },
                {
                    "type": "list",
                    "items": [
                        "Click Add Crypto to add a crypto holding.",
                        "Click Add Stock to add a stock or ETF holding.",
                        "Search by ticker or asset name.",
                        "Enter your quantity and save.",
                        "Use Edit to update quantity or remove a holding.",
                    ],
                },
                {
                    "type": "note",
                    "text": "Portfolio net worth is separate from the account balance net worth shown on the Dashboard.",
                },
            ],
        },
        {
            "id": "profile-settings",
            "title": "Profile & Settings",
            "subtitle": "Manage personal configuration",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Profile controls your accounts, categories, savings goals, language preference, balance snapshots, and data deletion settings.",
                },
                {
                    "type": "table",
                    "headers": ["Action", "Where to go"],
                    "rows": [
                        ["Add account", "Profile → Accounts → Add account"],
                        ["Update account balance", "Profile → Accounts → Balance field → Save"],
                        ["Rename account", "Profile → Accounts → Rename"],
                        ["Disable or enable account", "Profile → Accounts → Disable / Enable"],
                        ["Set default import account", "Profile → Accounts → Make default"],
                        ["Switch language", "Avatar menu or mobile menu → EN / LT"],
                        ["Delete account", "Profile → Delete account"],
                        ["Delete transaction data", "Transactions → Data deletion section"],
                    ],
                },
                {
                    "type": "note",
                    "text": "Account deletion and transaction data deletion use a 24-hour grace period before final removal.",
                },
            ],
        },
        {
            "id": "quick-reference",
            "title": "Quick Reference",
            "subtitle": "Where to find common actions",
            "body": [
                {
                    "type": "table",
                    "headers": ["I want to...", "Where to go"],
                    "rows": [
                        ["See total net worth", "Dashboard → top card"],
                        ["Upload a bank statement", "Transactions → Upload Statement card"],
                        ["Undo a file upload", "Transactions → Undo last upload"],
                        ["Categorize transactions quickly", "Transactions → category dropdowns → Apply Changes"],
                        ["Review uncertain AI suggestions", "Transactions → Low-confidence"],
                        ["Find uncategorized transactions", "Transactions → Uncategorized"],
                        ["Hide an internal transfer", "Transactions → Edit → Delete section"],
                        ["Restore deleted transaction", "Transactions → Deleted → Restore"],
                        ["Read AI financial report", "Reports"],
                        ["Track crypto or stocks", "Portfolio"],
                        ["Create a savings goal", "Profile → Savings Goals"],
                        ["Detect subscriptions", "Statistics → Review subscriptions"],
                        ["Set category spending cap", "Profile → Categories"],
                        ["Log out", "Avatar menu → Log Out"],
                    ],
                },
            ],
        },
    ],

    "lt": [
        {
            "id": "introduction",
            "title": "Įvadas",
            "subtitle": "Nuo nulio iki finansinio aiškumo",
            "body": [
                image(
                    "lt",
                    "mascot.png",
                    "Money Compass talismanas",
                    "Money Compass — asmeninių finansų valdymas.",
                    variant="mascot",
                ),
                {
                    "type": "paragraph",
                    "text": "Money Compass yra internetinė programa asmeniniams finansams sekti. Banko išrašus eksportuojate iš savo banko ir importuojate į Money Compass — tiesioginis ryšys su banku nereikalingas.",
                },
                {
                    "type": "paragraph",
                    "text": "Galite sekti išlaidas pagal kategorijas, stebėti grynąją vertę, naudoti DI kategorizavimą, peržiūrėti diagramas, valdyti investicijas ir gauti DI sugeneruotas finansines ataskaitas.",
                },
                {
                    "type": "note",
                    "text": "Money Compass nesijungia prie jūsų banko tiesiogiai. Jūs patys kontroliuojate duomenis eksportuodami ir įkeldami išrašus rankiniu būdu.",
                },
            ],
        },
        {
            "id": "programos-apzvalga",
            "title": "Programos apžvalga",
            "subtitle": "Pagrindinės Money Compass sritys",
            "body": [
                image(
                    "lt",
                    "desktop-nav.png",
                    "Darbalaukio navigacijos pavyzdys",
                    "Darbalaukio navigacija.",
                ),
                image(
                    "lt",
                    "mobile-nav.png",
                    "Mobilios navigacijos pavyzdys",
                    "Mobilioji navigacija.",
                ),
                {
                    "type": "table",
                    "headers": ["Skyrius", "Ką čia darote"],
                    "rows": [
                        ["Apžvalga", "Matote bendrą grynąją vertę, pajamas ir išlaidas, kategorijų analizę, taupymo tikslus ir mėnesinį balansą."],
                        ["Statistika", "Peržiūrite viso laikotarpio sumas, pajamų šaltinius, prenumeratas, pardavėjus ir kategorizavimo aprėptį."],
                        ["Ataskaitos", "Skaitote DI sugeneruotas mėnesines ir savaitines finansų apžvalgas."],
                        ["Portfelis", "Sekate kripto ir akcijų / ETF pozicijas su realiomis kainomis ir bendra verte."],
                        ["Operacijos", "Įkeliate banko išrašus, naršote, filtruojate, kategorizuojate, paslepiate ir atkuriate operacijas."],
                        ["Profilis / Nustatymai", "Valdote sąskaitas, kategorijas, taupymo tikslus, kalbą ir duomenų ištrynimą."],
                    ],
                },
                {
                    "type": "note",
                    "text": "Telefone naudokite apatinę navigaciją: Pagrindinis, Investicijos, Statistika, Operacijos ir Meniu. Kompiuteryje naudokite viršutinę navigacijos juostą.",
                },
                {
                    "type": "heading",
                    "text": "Kas Money Compass nėra",
                },
                {
                    "type": "list",
                    "items": [
                        "Programa nesijungia prie jūsų banko tiesiogiai.",
                        "Atskiros mobiliosios programėlės nėra, bet svetainė pritaikyta telefonui.",
                        "Viešos API nėra.",
                        "Sąskaitų likučiai skaičiuojami iš importuotų operacijų po to, kai nustatote pradinį likutį.",
                    ],
                },
            ],
        },
        {
            "id": "pradzia",
            "title": "Pradžia",
            "subtitle": "Registracija, sąskaitos ir pradinis nustatymas",
            "body": [
                {
                    "type": "heading",
                    "text": "Registracija ir prisijungimas",
                },
                {
                    "type": "list",
                    "items": [
                        "Eikite į programos adresą ir paspauskite Registruotis.",
                        "Įveskite savo duomenis ir susikurkite paskyrą.",
                        "Kitą kartą paspauskite Prisijungti ir įveskite vartotojo vardą bei slaptažodį.",
                        "Norėdami atsijungti, paspauskite avatarą arba inicialus viršuje dešinėje ir pasirinkite Atsijungti.",
                    ],
                },
                {
                    "type": "heading",
                    "text": "Pradinis nustatymas — 5 žingsniai",
                },
                {
                    "type": "table",
                    "headers": ["Žingsnis", "Ką daryti"],
                    "rows": [
                        ["1. Kategorijos", "Peržiūrėkite numatytąsias kategorijas. Pridėkite reikalingas ir pašalinkite nenaudojamas."],
                        ["2. Įkėlimas", "Įkelkite pirmą CSV arba XLSX banko išrašą."],
                        ["3. Nustatyti likutį", "Eikite į Profilį ir nustatykite dabartinį kiekvienos finansinės sąskaitos likutį."],
                        ["4. Apmokyti DI", "Rankiniu būdu priskirkite kategorijas bent 30 operacijų, kad DI išmoktų jūsų įpročius."],
                        ["5. Paruošta", "DI automatinis kategorizavimas tampa aktyvus, kai pradinis nustatymas baigtas."],
                    ],
                },
                {
                    "type": "note",
                    "text": "DI automatinis kategorizavimas įsijungia tik tada, kai rankiniu būdu sukategorizuojate bent 30 operacijų.",
                },
                {
                    "type": "heading",
                    "text": "Finansinių sąskaitų nustatymas",
                },
                image(
                    "lt",
                    "accounts-setup.png",
                    "Finansinių sąskaitų nustatymo pavyzdys",
                    "Finansinių sąskaitų nustatymas profilyje.",
                ),
                {
                    "type": "list",
                    "items": [
                        "Atidarykite Profilį per avataro meniu arba telefone per Meniu → Nustatymai.",
                        "Pridėkite kiekvieną naudojamą sąskaitą, pvz. Revolut, SEB, Grynieji, Taupomoji ar Investicinė.",
                        "Pasirinkite tinkamą tipą: Bankas, Grynieji, Taupomoji arba Investicinė.",
                        "Po pirmojo CSV įkėlimo įveskite dabartinį kiekvienos sąskaitos likutį ir išsaugokite.",
                    ],
                },
            ],
        },
        {
            "id": "operaciju-importavimas",
            "title": "Operacijų importavimas",
            "subtitle": "Saugus banko išrašų įkėlimas",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Operacijos yra Money Compass pagrindas. Eksportuojate failą iš savo banko ir įkeliate jį į programą. Money Compass apdoroja failą, praleidžia dublikatus ir prideda naujas eilutes į operacijų istoriją.",
                },
                {
                    "type": "heading",
                    "text": "Palaikomi išrašų formatai",
                },
                {
                    "type": "list",
                    "items": [
                        "SEB bankas",
                        "Swedbank",
                        "Revolut",
                        "Bendriniai CSV arba XLSX failai su datos, pardavėjo ir sumos stulpeliais",
                    ],
                },
                {
                    "type": "heading",
                    "text": "Įkėlimo eiga",
                },
                image(
                    "lt",
                    "upload-statement.png",
                    "Banko išrašo įkėlimo forma",
                    "Išrašo įkėlimo kortelė.",
                ),
                {
                    "type": "list",
                    "items": [
                        "Atidarykite Operacijų puslapį.",
                        "Pasirinkite tikslinę sąskaitą.",
                        "Pasirinkite banko formatą.",
                        "Pasirinkite CSV arba Excel failą.",
                        "Paspauskite Įkelti ir peržiūrėkite importo suvestinę.",
                    ],
                },
                {
                    "type": "note",
                    "text": "Tą patį failą galima saugiai įkelti pakartotinai. Esamos eilutės aptinkamos kaip dublikatai ir praleidžiamos.",
                },
                {
                    "type": "heading",
                    "text": "Atšaukti paskutinį įkėlimą",
                },
                {
                    "type": "paragraph",
                    "text": "Jei įkėlėte netinkamą failą arba pasirinkote ne tą sąskaitą, Operacijų puslapyje naudokite Atšaukti paskutinį įkėlimą. Tai negrįžtamai ištrina paskutinės importo partijos operacijas.",
                },
                {
                    "type": "heading",
                    "text": "Pridėti operaciją rankiniu būdu",
                },
                {
                    "type": "paragraph",
                    "text": "Grynųjų pirkimams arba operacijoms, kurių nėra banko išraše, naudokite Pridėti rankiniu būdu Operacijų puslapyje.",
                },
            ],
        },
        {
            "id": "operacijos",
            "title": "Operacijų naršymas ir valdymas",
            "subtitle": "Filtravimas, kategorizavimas, paslėpimas ir atkūrimas",
            "body": [
                {
                    "type": "heading",
                    "text": "Greitos nuorodos",
                },
                {
                    "type": "table",
                    "headers": ["Nuoroda", "Ką daro"],
                    "rows": [
                        ["DI kategorizuotos", "Rodo operacijas, kurias sukategorizavo DI."],
                        ["Mažo pasitikėjimo", "Rodo DI pasiūlymus, kuriuos reikia peržiūrėti rankiniu būdu."],
                        ["Nekategorizuotos", "Rodo operacijas be tinkamos kategorijos."],
                        ["Ištrintos", "Rodo paslėptas operacijas, kurias galima atkurti."],
                    ],
                },
                {
                    "type": "heading",
                    "text": "Filtravimas",
                },
                image(
                    "lt",
                    "filter-search.png",
                    "Operacijų filtravimo ir paieškos forma",
                    "Operacijų filtravimas ir paieška.",
                ),
                {
                    "type": "paragraph",
                    "text": "Filtravimo ir paieškos kortelėje galite filtruoti pagal sąskaitą, pardavėją, datų intervalą, sumos intervalą, srautą ir kategoriją.",
                },
                {
                    "type": "heading",
                    "text": "Kategorijų priskyrimas sąraše",
                },
                {
                    "type": "paragraph",
                    "text": "Operacijų lentelėje pakeiskite Kategorijos išskleidžiamąjį sąrašą bet kurioje eilutėje. Atsiras laukiančio pakeitimo indikatorius ir lipni Pritaikyti pakeitimus juosta.",
                },
                {
                    "type": "heading",
                    "text": "Operacijos redagavimas",
                },
                image(
                    "lt",
                    "transaction-edit.png",
                    "Operacijos redagavimo puslapis",
                    "Operacijos redagavimas.",
                ),
                {
                    "type": "paragraph",
                    "text": "Paspauskite Redaguoti prie operacijos, kad pakeistumėte kategoriją arba pridėtumėte vartotojo pastabą. Rankiniu būdu vartotojo pasirinkta kategorija yra apsaugota ir DI jos neperrašys.",
                },
                {
                    "type": "heading",
                    "text": "Minkštas trynimas ir atkūrimas",
                },
                {
                    "type": "paragraph",
                    "text": "Minkštas trynimas paslepia operaciją iš diagramų ir sąrašų, bet palieka jos atpažinimo kodą. Tai neleidžia tai pačiai eilutei atsikurti pakartotinai įkėlus banko failą.",
                },
                {
                    "type": "heading",
                    "text": "Grąžinimų aptikimas",
                },
                image(
                    "lt",
                    "refund-detection.png",
                    "Grąžinimų aptikimo skiltis",
                    "Rastų grąžinimų skiltis.",
                ),
                {
                    "type": "paragraph",
                    "text": "Money Compass aptinka galimus grąžinimus, kai viena išeinanti ir viena gaunama operacija turi tiksliai tokią pačią sumą, tą pačią valiutą ir ne didesnį kaip 10 dienų skirtumą. Galite abi operacijas pašalinti iš diagramų arba ignoruoti pasiūlymą.",
                },
            ],
        },
        {
            "id": "kategorijos",
            "title": "Kategorijos",
            "subtitle": "Supraskite, kur keliauja jūsų pinigai",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Kategorijos leidžia žymėti operacijas, kad aiškiai matytumėte, kur keliauja jūsų pinigai.",
                },
                {
                    "type": "heading",
                    "text": "Kategorijų kūrimas",
                },
                image(
                    "lt",
                    "categories.png",
                    "Kategorijų valdymo skiltis",
                    "Kategorijų valdymas.",
                ),
                {
                    "type": "paragraph",
                    "text": "Eikite į Profilį, raskite Kategorijų skiltį, įveskite naujos kategorijos pavadinimą ir paspauskite Pridėti.",
                },
                {
                    "type": "list",
                    "items": [
                        "Maistas ir bakalėja",
                        "Kavinės ir restoranai",
                        "Transportas",
                        "Nuoma / sąskaitos",
                        "Prenumeratos",
                        "Pajamos",
                        "Sveikata",
                        "Pramogos",
                        "Apsipirkimas",
                    ],
                },
                {
                    "type": "note",
                    "text": "Įmontuotos kategorijos Kita negalima ištrinti. Ji naudojama kaip atsarginė kategorija, kai kategorija pašalinama arba kai DI nėra tikras.",
                },
                {
                    "type": "heading",
                    "text": "Išlaidų limitai",
                },
                image(
                    "lt",
                    "category-caps.png",
                    "Kategorijų išlaidų limitų skiltis",
                    "Mėnesiniai kategorijų limitai.",
                ),
                {
                    "type": "paragraph",
                    "text": "Kiekvienai kategorijai galite nustatyti mėnesinį išlaidų limitą. Kai limitas nustatytas, Apžvalgos kategorijų diagramoje rodoma limito linija.",
                },
                {
                    "type": "heading",
                    "text": "Kategorijų trynimas",
                },
                {
                    "type": "paragraph",
                    "text": "Ištrynus kategoriją, visos tos kategorijos operacijos perkeliamos į Kita.",
                },
            ],
        },
        {
            "id": "di-kategorizavimas",
            "title": "DI kategorizavimas",
            "subtitle": "Automatinis operacijų kategorizavimas",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Money Compass naudoja DI, kad pasiūlytų operacijų kategorijas. Tai sumažina rankinį darbą po didelių importų.",
                },
                {
                    "type": "note",
                    "text": "DI kategorizavimas prasideda tik baigus pradinį nustatymą ir rankiniu būdu sukategorizavus bent 30 operacijų.",
                },
                {
                    "type": "table",
                    "headers": ["Pasitikėjimas", "Veiksmas"],
                    "rows": [
                        ["90% arba daugiau", "Automatiškai pritaikoma."],
                        ["80%–89%", "Automatiškai pritaikoma kaip kategorija."],
                        ["Mažiau nei 80%", "Atidedama rankinei peržiūrai Mažo pasitikėjimo puslapyje."],
                        ["Vartotojo nustatyta kategorija", "DI niekada neperrašo."],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "DI mokosi iš jūsų jau sukategorizuotų operacijų. Kuo tiksliau kategorizuojate rankiniu būdu, tuo geresni tampa būsimi pasiūlymai.",
                },
            ],
        },
        {
            "id": "apzvalga",
            "title": "Apžvalga",
            "subtitle": "Finansinė suvestinė vienu žvilgsniu",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Apžvalgoje rodoma bendra grynoji vertė, sąskaitų sudėtis, likučio istorija, taupymo tikslai, pajamos ir išlaidos, mėnesinis balansas ir išlaidos pagal kategoriją.",
                },
                {
                    "type": "heading",
                    "text": "Bendra grynoji vertė",
                },
                image(
                    "lt",
                    "dashboard-net-worth.png",
                    "Bendros grynosios vertės kortelė",
                    "Bendra grynoji vertė.",
                ),
                {
                    "type": "paragraph",
                    "text": "Grynoji vertė skaičiuojama pagal sąskaitų pradinius likučius ir importuotas operacijas. Jei skaičius nukrypsta dėl trūkstamų įkėlimų, Profilyje įveskite teisingą likutį iš naujo.",
                },
                {
                    "type": "heading",
                    "text": "Sąskaitos ir turtas",
                },
                image(
                    "lt",
                    "accounts-assets.png",
                    "Sąskaitų ir turto lentelė",
                    "Sąskaitos ir turtas.",
                ),
                {
                    "type": "heading",
                    "text": "Grynosios vertės istorija",
                },
                image(
                    "lt",
                    "net-worth-history.png",
                    "Grynosios vertės istorijos diagrama",
                    "Grynosios vertės istorijos diagrama.",
                ),
                {
                    "type": "heading",
                    "text": "Taupymo tikslai",
                },
                image(
                    "lt",
                    "savings-goals.png",
                    "Taupymo tikslų eigos juostos",
                    "Taupymo tikslai.",
                ),
                {
                    "type": "heading",
                    "text": "Pajamos ir išlaidos",
                },
                image(
                    "lt",
                    "income-vs-spending.png",
                    "Pajamų ir išlaidų diagrama",
                    "Pajamų ir išlaidų diagrama.",
                ),
                {
                    "type": "heading",
                    "text": "Mėnesinis balansas",
                },
                image(
                    "lt",
                    "net-by-month.png",
                    "Mėnesinio balanso lentelė",
                    "Mėnesinis balansas.",
                ),
                {
                    "type": "heading",
                    "text": "Išlaidos pagal kategoriją",
                },
                image(
                    "lt",
                    "spending-per-category.png",
                    "Išlaidų pagal kategoriją diagrama",
                    "Išlaidos pagal kategoriją.",
                ),
                {
                    "type": "paragraph",
                    "text": "Kategorijų diagrama leidžia perjungti kategorijas, keisti diagramos tipą, matyti mėnesio pardavėjų suskirstymą ir atidaryti filtruotas konkretaus pardavėjo operacijas.",
                },
            ],
        },
        {
            "id": "statistika",
            "title": "Statistika",
            "subtitle": "Gilesnė finansų analizė",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Statistikos puslapyje matote viso laikotarpio pajamas, išlaidas, grynąjį rezultatą, mėnesinius vidurkius, operacijų skaičių, kategorizavimo aprėptį ir pardavėjų analizę.",
                },
                {
                    "type": "heading",
                    "text": "Pajamų šaltiniai",
                },
                {
                    "type": "paragraph",
                    "text": "Money Compass aptinka pajamų šaltinius iš gaunamų operacijų. Juos galite peržiūrėti, sekti, nebesekti arba vėl pradėti sekti.",
                },
                {
                    "type": "heading",
                    "text": "Prenumeratos",
                },
                {
                    "type": "paragraph",
                    "text": "Money Compass aptinka pasikartojančius išeinančius mokėjimus kaip galimas prenumeratas. Kandidatus galite patvirtinti, atmesti arba vėl pradėti sekti anksčiau nebesektas prenumeratas.",
                },
            ],
        },
        {
            "id": "ataskaitos",
            "title": "Ataskaitos",
            "subtitle": "DI sugeneruotos finansų apžvalgos",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Ataskaitos yra DI sugeneruotos jūsų finansų suvestinės, parašytos paprasta kalba.",
                },
                {
                    "type": "heading",
                    "text": "Mėnesinės ataskaitos",
                },
                {
                    "type": "paragraph",
                    "text": "Mėnesinės ataskaitos generuojamos automatiškai pasibaigus mėnesiui ir apima rašytinę suvestinę bei pagrindinius rodiklius.",
                },
                {
                    "type": "heading",
                    "text": "Savaitinės ataskaitos",
                },
                {
                    "type": "paragraph",
                    "text": "Savaitinės ataskaitos generuojamos automatiškai kiekvieną pirmadienį.",
                },
                {
                    "type": "heading",
                    "text": "Likučių suderinimas",
                },
                {
                    "type": "paragraph",
                    "text": "Likučių suderinimo lentelė lygina iš eilės einančias likučio momentines reikšmes ir tikrina, ar importuotos operacijos paaiškina skirtumą tarp jų.",
                },
            ],
        },
        {
            "id": "portfelis",
            "title": "Portfelis",
            "subtitle": "Kripto ir akcijų / ETF pozicijų sekimas",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Portfelio puslapyje galite sekti kriptovaliutų ir akcijų / ETF pozicijas su dabartinėmis EUR kainomis ir apskaičiuota bendra verte.",
                },
                {
                    "type": "list",
                    "items": [
                        "Paspauskite Pridėti kripto, kad pridėtumėte kripto poziciją.",
                        "Paspauskite Pridėti akciją, kad pridėtumėte akciją arba ETF.",
                        "Ieškokite pagal žymeklį arba turto pavadinimą.",
                        "Įveskite kiekį ir išsaugokite.",
                        "Naudokite Redaguoti, kad pakeistumėte kiekį arba pašalintumėte poziciją.",
                    ],
                },
                {
                    "type": "note",
                    "text": "Portfelio grynoji vertė yra atskira nuo sąskaitų likučių grynosios vertės, rodomos Apžvalgoje.",
                },
            ],
        },
        {
            "id": "profilis-nustatymai",
            "title": "Profilis ir nustatymai",
            "subtitle": "Asmeninių nustatymų valdymas",
            "body": [
                {
                    "type": "paragraph",
                    "text": "Profilyje valdote sąskaitas, kategorijas, taupymo tikslus, kalbą, likučio momentines reikšmes ir duomenų ištrynimo nustatymus.",
                },
                {
                    "type": "table",
                    "headers": ["Veiksmas", "Kur eiti"],
                    "rows": [
                        ["Pridėti sąskaitą", "Profilis → Sąskaitos → Pridėti sąskaitą"],
                        ["Atnaujinti sąskaitos likutį", "Profilis → Sąskaitos → Likučio laukelis → Išsaugoti"],
                        ["Pervadinti sąskaitą", "Profilis → Sąskaitos → Pervadinti"],
                        ["Išjungti arba įjungti sąskaitą", "Profilis → Sąskaitos → Išjungti / Įjungti"],
                        ["Nustatyti numatytąją importo sąskaitą", "Profilis → Sąskaitos → Numatyti"],
                        ["Pakeisti kalbą", "Avataro meniu arba mobilus meniu → EN / LT"],
                        ["Ištrinti paskyrą", "Profilis → Ištrinti paskyrą"],
                        ["Ištrinti operacijų duomenis", "Operacijos → Duomenų trynimo skiltis"],
                    ],
                },
                {
                    "type": "note",
                    "text": "Paskyros ir operacijų duomenų ištrynimui taikomas 24 valandų atšaukimo laikotarpis.",
                },
            ],
        },
        {
            "id": "greita-nuorodu-lentele",
            "title": "Greita nuorodų lentelė",
            "subtitle": "Kur rasti dažniausius veiksmus",
            "body": [
                {
                    "type": "table",
                    "headers": ["Noriu...", "Kur eiti"],
                    "rows": [
                        ["Pamatyti grynąją vertę", "Apžvalga → viršutinė kortelė"],
                        ["Įkelti banko išrašą", "Operacijos → Įkelti išrašą"],
                        ["Atšaukti failo įkėlimą", "Operacijos → Atšaukti paskutinį įkėlimą"],
                        ["Greitai kategorizuoti operacijas", "Operacijos → kategorijų sąrašai → Pritaikyti pakeitimus"],
                        ["Peržiūrėti netikslius DI pasiūlymus", "Operacijos → Mažo pasitikėjimo"],
                        ["Rasti nekategorizuotas operacijas", "Operacijos → Nekategorizuotos"],
                        ["Paslėpti vidinį pervedimą", "Operacijos → Redaguoti → Trynimo sekcija"],
                        ["Atkurti ištrintą operaciją", "Operacijos → Ištrintos → Atkurti"],
                        ["Skaityti DI finansinę ataskaitą", "Ataskaitos"],
                        ["Sekti kripto arba akcijas", "Portfelis"],
                        ["Sukurti taupymo tikslą", "Profilis → Taupymo tikslai"],
                        ["Aptikti prenumeratas", "Statistika → Peržiūrėti prenumeratas"],
                        ["Nustatyti kategorijos išlaidų limitą", "Profilis → Kategorijos"],
                        ["Atsijungti", "Avataro meniu → Atsijungti"],
                    ],
                },
            ],
        },
    ],
}