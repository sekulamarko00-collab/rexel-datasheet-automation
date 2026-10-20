from pathlib import Path
from urllib.parse import urljoin
import re

from playwright.sync_api import sync_playwright

from file_utils import clean_filename, unique_path


# ==========================================================
# OPŠTE FUNKCIJE
# ==========================================================

def position_to_group_folder(position):
    """
    '1.20.017' -> '1.20'
    '1.30.005' -> '1.30'
    """
    parts = str(position).strip().split(".")

    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"

    return str(position).strip()


def format_position_prefix(positions):
    """
    ['1.20.001', '1.20.002', '1.20.003']
    ->
    '1.20.001,002,003'
    """
    positions = sorted(set(str(p).strip() for p in positions))

    if not positions:
        return ""

    first = positions[0]
    parts = first.split(".")

    if len(parts) < 3:
        return ",".join(positions)

    base = f"{parts[0]}.{parts[1]}"
    suffixes = []
    mixed_groups = False

    for pos in positions:
        pos_parts = pos.split(".")

        if len(pos_parts) >= 3 and f"{pos_parts[0]}.{pos_parts[1]}" == base:
            suffixes.append(pos_parts[2])
        else:
            mixed_groups = True
            break

    if mixed_groups:
        return ",".join(positions)

    return f"{base}.{','.join(suffixes)}"


def build_combined_filename(positions, original_name):
    """
    positions: ['1.20.001', '1.20.002']
    original_name: de_LS_981_WW_ad.pdf

    result:
    1.20.001,002_de_LS_981_WW_ad.pdf
    """
    prefix = format_position_prefix(positions)
    return f"{prefix}_{original_name}"


def is_real_pdf_response(response, body):
    """
    Stroga PDF provera.

    Fajl mora stvarno početi sa:
    %PDF

    Ovo sprečava snimanje:
    - datasheet.php
    - HTML stranica
    - redirect fajlova
    - lažnih 4 KB / 5 KB PDF-ova
    """
    if not body:
        return False

    body_start = body[:100].lstrip()
    return body_start.startswith(b"%PDF")


def auto_scroll(page):
    """
    Skroluje stranicu da se učitaju dokumenti.
    """
    page.evaluate("""
        async () => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 1200;
                const timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    totalHeight += distance;

                    if (totalHeight >= document.body.scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 80);
            });
        }
    """)


def get_filename_from_response(response, fallback_url, article_number):
    """
    Pokušava da uzme ime fajla iz HTTP headera.
    Ako ne može, koristi URL.
    Ako dobije .php, preimenuje u normalan PDF naziv.
    """
    content_disposition = response.headers.get("content-disposition", "")

    match = re.search(
        r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?',
        content_disposition
    )

    if match:
        filename = clean_filename(match.group(1))
    else:
        filename = fallback_url.split("/")[-1].split("?")[0]
        filename = clean_filename(filename)

    if not filename or "." not in filename:
        filename = f"{article_number}_Produktdatenblatt.pdf"

    if filename.lower().endswith(".php"):
        filename = f"{article_number}_Produktdatenblatt.pdf"

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    return filename


# ==========================================================
# WÜRTH LOGIKA
# ==========================================================

def is_wurth_article(article_number):
    """
    Würth artikli počinju sa W, čak i ako ćelija ima dodatne razmake/količinu.

    Primeri:
    W0975259125
    W090632660   100
    """
    return bool(re.search(r"\bW\s*\d{5,}", str(article_number), re.IGNORECASE))


def clean_wurth_article(article_number):
    """
    W0975259125 -> 0975259125
    W090632660   100 -> 090632660
    """
    value = str(article_number).strip().upper()

    match = re.search(r"W\s*(\d{5,})", value)
    if match:
        return match.group(1)

    match = re.search(r"\d{5,}", value)
    if match:
        return match.group(0)

    return value


def normalize_wurth_article(article_number):
    """
    W090632660   100 -> W090632660
    """
    digits = clean_wurth_article(article_number)
    return f"W{digits}"


def is_electrical_wurth_product(page):
    """
    Proverava da li Würth proizvod pripada elektro opremi.

    Dozvoljava:
    - elektro instalacioni materijal
    - cevi
    - obujmice / Abstandschelle
    - kablovski kanali
    - razvodne kutije
    - stezaljke
    - prekidače / utičnice

    Blokira:
    - tiple
    - šrafove / vijke
    - matice
    - podloške
    - ankere
    - burgije
    - eksere
    - alat
    """

    try:
        title = page.locator("h1").first.inner_text(timeout=5000).lower()
    except Exception:
        title = page.title().lower()

    current_url = page.url.lower()
    combined = f"{title} {current_url}"

    allowed_words = [
        "elektro",
        "elektroinstallation",
        "verlegesysteme",
        "installationsrohr",
        "elektro-installationsrohr",
        "isolierrohr",
        "kabel",
        "leitung",
        "conduit",
        "rohr",
        "schalter",
        "steck",
        "steckdose",
        "dose",
        "abzweigdose",
        "verteilerdose",
        "verteiler",
        "klemme",
        "kanal",
        "kabelkanal",
        "abstandschelle",
        "schelle",
        "befestigungsschelle",
        "rohrschelle",
        "kabelschelle",
    ]

    blocked_words = [
        # tiple / ankeri
        "dübel",
        "duebel",
        "duebels",
        "dübelset",
        "duebelset",
        "universaldübel",
        "universalduebel",
        "hohlraumdübel",
        "hohlraumduebel",
        "anker",
        "bolzenanker",
        "schlaganker",
        "einschlaganker",
        "spreizanker",
        "betonanker",

        # šrafovi / vijci
        "schraube",
        "schrauben",
        "screw",
        "screws",
        "gewindeschraube",
        "holzschraube",
        "blechschraube",
        "bohrschraube",
        "spanplattenschraube",
        "sechskantschraube",
        "zylinderschraube",
        "senkschraube",
        "linsenschraube",
        "vijak",
        "vijci",
        "šraf",
        "sraf",
        "šrafovi",
        "srafovi",

        # matice / podloške
        "mutter",
        "muttern",
        "nut",
        "nuts",
        "scheibe",
        "scheiben",
        "washer",
        "washers",
        "unterlegscheibe",
        "federring",
        "sicherungsmutter",

        # ekseri / klinovi
        "nagel",
        "nägel",
        "naegel",
        "stift",
        "stifte",
        "pin",
        "pins",

        # burgije / alat
        "bohrer",
        "drill",
        "bohrkrone",
        "senker",
        "fräser",
        "fraeser",
        "säge",
        "saege",
        "saw",
        "bit",
        "bits",
        "werkzeug",
        "tool",
        "tools",

        # hemija / montažni materijal koji ne želimo
        "kleber",
        "klebstoff",
        "silikon",
        "acryl",
        "dichtstoff",
        "schaum",
        "montageschaum",
    ]

    # Ako naslov/URL sadrži nešto blokirano — preskoči odmah
    if any(word in combined for word in blocked_words):
        return False

    # Ako sadrži elektro reči — prihvati
    if any(word in combined for word in allowed_words):
        return True

    # Ako ne znamo šta je — bolje preskočiti nego skinuti pogrešno
    return False


def find_wurth_product_page(page, original_article_number, wurth_number):
    """
    Traži Würth proizvod.

    Primer:
    W0971601420 -> 0971601420.sku

    Radi:
    1. Würth search sa W brojem
    2. Würth search bez W
    3. Frontend search varijante
    4. Traži link koji sadrži 0971601420.sku
    5. Ako je stranica već .sku URL, prihvata je
    """

    normalized_w = f"W{wurth_number}"

    search_urls = [
        (
            "https://eshop.wuerth.de/is-bin/INTERSHOP.enfinity/"
            f"WFS/3008-B1-Site/de_DE/-/EUR/ViewParametricSearch-SimpleOfferSearch?SearchTerm={normalized_w}"
        ),
        (
            "https://eshop.wuerth.de/is-bin/INTERSHOP.enfinity/"
            f"WFS/3008-B1-Site/de_DE/-/EUR/ViewParametricSearch-SimpleOfferSearch?SearchTerm={wurth_number}"
        ),
        f"https://eshop.wuerth.de/de/DE/EUR/?VisibleSearchTerm={normalized_w}",
        f"https://eshop.wuerth.de/?VisibleSearchTerm={normalized_w}",
    ]

    for search_url in search_urls:
        print(f"[WÜRTH] Search URL: {search_url}")

        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)

        current_url = page.url
        title = page.title()

        print(f"[WÜRTH] Current URL: {current_url}")
        print(f"[WÜRTH] Search title: {title}")

        # Ako nas Würth odmah prebaci na product URL
        if ".sku" in current_url.lower() and wurth_number in current_url:
            print("[WÜRTH] Direktno otvorena product stranica.")
            return True

        links = page.evaluate("""
            () => {
                const result = [];

                document.querySelectorAll("a").forEach(a => {
                    result.push({
                        text: (a.innerText || a.textContent || "").trim(),
                        href: a.href || a.getAttribute("href") || ""
                    });
                });

                return result;
            }
        """)

        exact_candidates = []
        sku_candidates = []

        for link in links:
            text = link.get("text", "").strip()
            href = link.get("href", "").strip()

            if not href:
                continue

            href_lower = href.lower()
            text_lower = text.lower()

            # Najvažnije: traži baš 0971601420.sku
            if f"{wurth_number}.sku" in href_lower:
                exact_candidates.append(href)

            # Dodatno: ako link ima .sku i broj u href/text
            elif ".sku" in href_lower and (wurth_number in href or normalized_w.lower() in text_lower):
                exact_candidates.append(href)

            # Rezervno: svi .sku linkovi
            elif ".sku" in href_lower:
                sku_candidates.append(href)

        if exact_candidates:
            product_url = urljoin(page.url, exact_candidates[0])
            print(f"[WÜRTH] Nađen exact product link: {product_url}")

            page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)

            return True

        # Ako ima samo jedan .sku kandidat, otvori ga
        if len(sku_candidates) == 1:
            product_url = urljoin(page.url, sku_candidates[0])
            print(f"[WÜRTH] Nađen jedan .sku kandidat: {product_url}")

            page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)

            if ".sku" in page.url.lower():
                return True

        print("[WÜRTH] Nema sigurnog product linka na ovoj search strani.")

    print(f"[WÜRTH FAIL] Nije pronađena product stranica za {original_article_number}")
    return False


def find_wurth_catalog_pdf_url(page):
    """
    Na nemačkom Würth sajtu traži:

    Dokumente -> Katalogseite als PDF 1

    Ne skida:
    - Zertifizierung/Zertifikat
    - Herstellererklärung
    - RoHS/REACH
    """

    auto_scroll(page)
    page.wait_for_timeout(1000)

    links = page.evaluate("""
        () => {
            const result = [];

            document.querySelectorAll("a").forEach(a => {
                result.push({
                    text: (a.innerText || a.textContent || "").trim(),
                    href: a.href || a.getAttribute("href") || ""
                });
            });

            return result;
        }
    """)

    blocked_words = [
        "zertifikat",
        "zertifizierung",
        "certificate",
        "hersteller",
        "herstellererklärung",
        "herstellererklaerung",
        "erklärung",
        "erklaerung",
        "declaration",
        "rohs",
        "reach",
        "safety",
        "konformität",
        "konformitaet",
    ]

    for link in links:
        text = link.get("text", "").strip()
        href = link.get("href", "").strip()

        text_lower = text.lower()
        href_lower = href.lower()
        combined = f"{text_lower} {href_lower}"

        if any(word in combined for word in blocked_words):
            continue

        if (
            "katalogseite als pdf" in combined
            or "catalog page as pdf" in combined
            or "catalogue page as pdf" in combined
            or ("katalogseite" in combined and "pdf" in combined)
            or ("media.wuerth.com" in href_lower and ".pdf" in href_lower)
        ):
            if href:
                print(f"[WÜRTH PDF FOUND] TEXT: {text}")
                print(f"[WÜRTH PDF FOUND] HREF: {href}")
                return href

    print("[WÜRTH FAIL] Nije pronađena Katalogseite als PDF.")
    return None


# ==========================================================
# REXEL LOGIKA
# ==========================================================

def resolve_exact_product_page(page, article_number):
    """
    Ako /p/{article_number} otvori listu rezultata,
    uzmi samo proizvod gde piše tačan Rexel Art.No.

    Ignoriše slučaj gde se broj pojavljuje kao Manufacturer's Item No.
    """

    article_number = str(article_number).strip()

    if f"/p/{article_number}" in page.url:
        return True

    page.wait_for_timeout(1500)

    product_href = page.evaluate(
        """
        (articleNumber) => {
            const wantedPatterns = [
                `Rexel Art.No.: ${articleNumber}`,
                `Rexel Art.No.:${articleNumber}`,
                `Rexel Art.Nr.: ${articleNumber}`,
                `Rexel Art.Nr.:${articleNumber}`,
                `Rexel Artikelnr.: ${articleNumber}`,
                `Rexel Artikelnr.:${articleNumber}`,
                `Rexel Art.-Nr.: ${articleNumber}`,
                `Rexel Art.-Nr.:${articleNumber}`
            ];

            const allElements = Array.from(document.querySelectorAll("*"));

            for (const el of allElements) {
                const txt = (el.innerText || el.textContent || "").trim();

                if (!txt) continue;

                const hasExactRexelNumber = wantedPatterns.some(pattern =>
                    txt.includes(pattern)
                );

                if (!hasExactRexelNumber) continue;

                let card = el;

                for (let i = 0; i < 10; i++) {
                    if (!card.parentElement) break;
                    card = card.parentElement;

                    const links = Array.from(card.querySelectorAll("a[href*='/p/']"));

                    if (links.length > 0) {
                        return links[0].href;
                    }
                }
            }

            return null;
        }
        """,
        article_number
    )

    if product_href:
        print(f"[EXACT MATCH] Nađen proizvod preko Rexel Art.No.: {article_number}")
        print(f"[EXACT MATCH] Otvaram: {product_href}")

        page.goto(product_href, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        return True

    print(f"[FAIL] Nije pronađen exact Rexel Art.No.: {article_number}")
    return False


def find_rexel_datasheet_url(page):
    """
    Rexel:
    Traži samo Produktdatenblatt / Product data sheet.

    Ne skida:
    - RoHS
    - REACH
    - Zertifikat
    - Herstellererklärung
    """

    auto_scroll(page)
    page.wait_for_timeout(800)

    links = page.evaluate("""
        () => {
            function collectLinks(root) {
                const result = [];

                root.querySelectorAll("a").forEach(a => {
                    result.push({
                        text: (a.innerText || a.textContent || "").trim(),
                        href: a.href || a.getAttribute("href") || ""
                    });
                });

                root.querySelectorAll("*").forEach(el => {
                    if (el.shadowRoot) {
                        result.push(...collectLinks(el.shadowRoot));
                    }
                });

                return result;
            }

            return collectLinks(document);
        }
    """)

    blocked_words = [
        "rohs",
        "reach",
        "zertifikat",
        "certificate",
        "hersteller",
        "erklärung",
        "erklaerung",
        "declaration",
        "deeplink",
        "deep link",
        "safety",
        "konformität",
        "konformitaet",
        "compliance",
    ]

    # Strogo: tekst mora biti Produktdatenblatt / Product data sheet
    for link in links:
        text = link.get("text", "").strip()
        href = link.get("href", "").strip()

        text_lower = text.lower()
        href_lower = href.lower()
        combined = f"{text_lower} {href_lower}"

        if any(word in combined for word in blocked_words):
            continue

        if (
            "produktdatenblatt" in text_lower
            or "product data sheet" in text_lower
        ):
            if href:
                print(f"[REXEL DATASHEET FOUND] TEXT: {text}")
                print(f"[REXEL DATASHEET FOUND] HREF: {href}")
                return href

    # Rezervno: URL ima datasheet
    for link in links:
        text = link.get("text", "").strip()
        href = link.get("href", "").strip()

        text_lower = text.lower()
        href_lower = href.lower()
        combined = f"{text_lower} {href_lower}"

        if any(word in combined for word in blocked_words):
            continue

        if (
            "redirect/datasheet" in href_lower
            or "/datasheet/" in href_lower
        ):
            if href:
                print(f"[REXEL DATASHEET FOUND BY URL] TEXT: {text}")
                print(f"[REXEL DATASHEET FOUND BY URL] HREF: {href}")
                return href

    print("[REXEL FAIL] Nije pronađen pravi Produktdatenblatt link.")
    return None


# ==========================================================
# GLAVNA KLASA
# ==========================================================

class RexelDownloader:
    def __init__(self, output_root="output", headless=True):
        self.output_root = Path(output_root)
        self.headless = headless

        # isti artikal -> jedan PDF
        # pozicije se dodaju u naziv fajla
        self.cache = {}

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=self.headless
        )

        self.context = self.browser.new_context(
            accept_downloads=True,
            locale="de-DE",
            viewport={"width": 1400, "height": 1000}
        )

        self.page = self.context.new_page()

    def stop(self):
        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()

    def _merge_cached_file(self, article_number, position, output_dir, group_folder, source):
        """
        Ako je isti artikal već skinut,
        ne pravi novi PDF nego preimenuje postojeći:

        1.20.001_de_LS_981_WW_ad.pdf
        ->
        1.20.001,002_de_LS_981_WW_ad.pdf
        """
        cached_data = self.cache[article_number]

        old_file = Path(cached_data["file"])
        original_name = cached_data["original_name"]
        positions = cached_data["positions"]

        if position not in positions:
            positions.append(position)

        new_filename = build_combined_filename(positions, original_name)
        new_path = output_dir / new_filename

        if old_file.exists():
            if old_file.resolve() != new_path.resolve():
                if new_path.exists():
                    new_path = unique_path(new_path)

                old_file.rename(new_path)

            cached_data["file"] = str(new_path)
            cached_data["positions"] = positions

            print(f"[CACHE-MERGE] {article_number} sada je: {new_path}")

            return {
                "success": True,
                "article_number": article_number,
                "position": position,
                "all_positions": ",".join(positions),
                "group_folder": group_folder,
                "file": str(new_path),
                "cached": True,
                "merged": True,
                "source": source,
                "error": ""
            }

        print(f"[CACHE WARNING] Cache fajl ne postoji, skidam ponovo: {old_file}")
        del self.cache[article_number]
        return None

    def _save_valid_pdf(self, response, body, article_number, position, output_dir, group_folder, source):
        """
        Snima PDF samo ako stvarno počinje sa %PDF.
        """
        if not is_real_pdf_response(response, body):
            content_type = response.headers.get("content-type", "").lower()
            preview = body[:120]

            print(f"[SKIP] Link nije pravi PDF za {article_number}")
            print(f"[SKIP] URL: {response.url}")
            print(f"[SKIP] Content-Type: {content_type}")
            print(f"[SKIP] Size: {len(body)} bytes")
            print(f"[SKIP] First bytes: {preview}")

            return {
                "success": False,
                "article_number": article_number,
                "position": position,
                "all_positions": position,
                "group_folder": group_folder,
                "file": "",
                "cached": False,
                "merged": False,
                "source": source,
                "error": "Downloaded file is not PDF"
            }

        original_name = get_filename_from_response(
            response=response,
            fallback_url=response.url,
            article_number=article_number
        )

        final_filename = build_combined_filename([position], original_name)
        final_path = unique_path(output_dir / final_filename)

        final_path.write_bytes(body)

        self.cache[article_number] = {
            "file": str(final_path),
            "original_name": original_name,
            "positions": [position]
        }

        print(f"[OK] Skinuto: {final_path}")

        return {
            "success": True,
            "article_number": article_number,
            "position": position,
            "all_positions": position,
            "group_folder": group_folder,
            "file": str(final_path),
            "cached": False,
            "merged": False,
            "source": source,
            "error": ""
        }

    def download_wurth_datasheet(self, article_number, position):
        """
        Würth artikli počinju sa W.

        W0975259125 -> traži 0975259125 na Würth sajtu.

        Skida:
        Dokumente -> Katalogseite als PDF 1
        """
        original_article_number = normalize_wurth_article(article_number)
        wurth_number = clean_wurth_article(article_number)
        position = str(position).strip()

        group_folder = position_to_group_folder(position)
        output_dir = self.output_root / group_folder
        output_dir.mkdir(parents=True, exist_ok=True)

        if original_article_number in self.cache:
            merged_result = self._merge_cached_file(
                article_number=original_article_number,
                position=position,
                output_dir=output_dir,
                group_folder=group_folder,
                source="Würth"
            )

            if merged_result is not None:
                return merged_result

        product_ok = find_wurth_product_page(
            page=self.page,
            original_article_number=original_article_number,
            wurth_number=wurth_number
        )

        if not product_ok:
            return {
                "success": False,
                "article_number": original_article_number,
                "position": position,
                "all_positions": position,
                "group_folder": group_folder,
                "file": "",
                "cached": False,
                "merged": False,
                "source": "Würth",
                "error": "Würth product not found"
            }

        print(f"[WÜRTH] URL: {self.page.url}")
        print(f"[WÜRTH] Title: {self.page.title()}")

        try:
            if not is_electrical_wurth_product(self.page):
                print(f"[WÜRTH SKIP] Nije elektro oprema: {original_article_number}")

                return {
                    "success": False,
                    "article_number": original_article_number,
                    "position": position,
                    "all_positions": position,
                    "group_folder": group_folder,
                    "file": "",
                    "cached": False,
                    "merged": False,
                    "source": "Würth",
                    "error": "Würth product is not electrical equipment"
                }
        except Exception as e:
            print(f"[WÜRTH WARNING] Ne mogu da proverim elektro filter: {e}")

        pdf_url = find_wurth_catalog_pdf_url(self.page)

        if not pdf_url:
            return {
                "success": False,
                "article_number": original_article_number,
                "position": position,
                "all_positions": position,
                "group_folder": group_folder,
                "file": "",
                "cached": False,
                "merged": False,
                "source": "Würth",
                "error": "Würth catalog PDF not found"
            }

        pdf_url = urljoin(self.page.url, pdf_url)

        print(f"[WÜRTH] PDF URL: {pdf_url}")

        response = self.context.request.get(
            pdf_url,
            max_redirects=10
        )

        if not response.ok:
            return {
                "success": False,
                "article_number": original_article_number,
                "position": position,
                "all_positions": position,
                "group_folder": group_folder,
                "file": "",
                "cached": False,
                "merged": False,
                "source": "Würth",
                "error": f"HTTP {response.status}"
            }

        body = response.body()

        return self._save_valid_pdf(
            response=response,
            body=body,
            article_number=original_article_number,
            position=position,
            output_dir=output_dir,
            group_folder=group_folder,
            source="Würth"
        )

    def download_rexel_datasheet(self, article_number, position):
        """
        Rexel artikli su obični brojevi.
        Skida samo Produktdatenblatt.
        """
        article_number = str(article_number).strip()
        position = str(position).strip()

        group_folder = position_to_group_folder(position)
        output_dir = self.output_root / group_folder
        output_dir.mkdir(parents=True, exist_ok=True)

        if article_number in self.cache:
            merged_result = self._merge_cached_file(
                article_number=article_number,
                position=position,
                output_dir=output_dir,
                group_folder=group_folder,
                source="Rexel"
            )

            if merged_result is not None:
                return merged_result

        product_url = f"https://www.rexel.de/p/{article_number}"

        print(f"[REXEL] Otvaram: {product_url}")

        self.page.goto(
            product_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        self.page.wait_for_timeout(1200)

        exact_ok = resolve_exact_product_page(self.page, article_number)

        if not exact_ok:
            return {
                "success": False,
                "article_number": article_number,
                "position": position,
                "all_positions": position,
                "group_folder": group_folder,
                "file": "",
                "cached": False,
                "merged": False,
                "source": "Rexel",
                "error": "Exact Rexel Art.No. not found"
            }

        print(f"[REXEL] URL: {self.page.url}")
        print(f"[REXEL] Title: {self.page.title()}")

        title_lower = self.page.title().lower()
        url_lower = self.page.url.lower()

        if "not found" in title_lower or "404" in title_lower or "not-found" in url_lower:
            return {
                "success": False,
                "article_number": article_number,
                "position": position,
                "all_positions": position,
                "group_folder": group_folder,
                "file": "",
                "cached": False,
                "merged": False,
                "source": "Rexel",
                "error": "Product not found"
            }

        datasheet_url = find_rexel_datasheet_url(self.page)

        if not datasheet_url:
            return {
                "success": False,
                "article_number": article_number,
                "position": position,
                "all_positions": position,
                "group_folder": group_folder,
                "file": "",
                "cached": False,
                "merged": False,
                "source": "Rexel",
                "error": "Datasheet not found"
            }

        datasheet_url = urljoin(self.page.url, datasheet_url)

        print(f"[REXEL] Datasheet URL: {datasheet_url}")

        response = self.context.request.get(
            datasheet_url,
            max_redirects=10
        )

        if not response.ok:
            return {
                "success": False,
                "article_number": article_number,
                "position": position,
                "all_positions": position,
                "group_folder": group_folder,
                "file": "",
                "cached": False,
                "merged": False,
                "source": "Rexel",
                "error": f"HTTP {response.status}"
            }

        body = response.body()

        return self._save_valid_pdf(
            response=response,
            body=body,
            article_number=article_number,
            position=position,
            output_dir=output_dir,
            group_folder=group_folder,
            source="Rexel"
        )

    def download_datasheet(self, article_number, position):
        """
        Glavni ulaz.

        Ako broj počinje sa W -> Würth
        Inače -> Rexel
        """
        article_number = str(article_number).strip()

        if is_wurth_article(article_number):
            return self.download_wurth_datasheet(
                article_number=article_number,
                position=position
            )

        return self.download_rexel_datasheet(
            article_number=article_number,
            position=position
        )


def download_datasheet(article_number, position="1.20.017"):
    """
    Ručni test jednog artikla.
    app.py koristi klasu RexelDownloader.
    """
    downloader = RexelDownloader(output_root="output", headless=False)

    try:
        downloader.start()
        return downloader.download_datasheet(article_number, position)
    finally:
        downloader.stop()


if __name__ == "__main__":
    download_datasheet("W0975259125", position="1.20.088")