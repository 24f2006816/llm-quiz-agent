import re, io, asyncio, json, base64
import aiohttp, pdfplumber, pandas as pd
from bs4 import BeautifulSoup

HTTP_TIMEOUT = aiohttp.ClientTimeout(total=90)

def extract_submit_url(html: str) -> str | None:
    # 1) explicit JSON block; 2) plain text; 3) href pattern
    m = re.search(r'https?://[^\s"<>]+/submit', html)
    return m.group(0) if m else None

def extract_download_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if href.startswith("http"):
            links.append(href)
    # also scan plaintext
    links += re.findall(r'https?://[^\s"<>]+', html)
    # uniques, keep order
    seen, uniq = set(), []
    for u in links:
        if u not in seen:
            seen.add(u); uniq.append(u)
    return uniq

async def http_get_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
        async with s.get(url, allow_redirects=True) as r:
            r.raise_for_status()
            return await r.read()

async def http_post_json(url: str, payload: dict) -> dict:
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as s:
        async with s.post(url, json=payload) as r:
            txt = await r.text()
            try:
                return json.loads(txt)
            except Exception:
                return {"raw": txt, "status": r.status}

def decode_atob_blocks(html: str) -> list[str]:
    # Find atob(`...`) or atob("...") payloads and decode them
    blocks = re.findall(r'atob\(\s*[`"\']([\s\S]*?)[`"\']\s*\)', html)
    out = []
    for b in blocks:
        try:
            out.append(base64.b64decode(b).decode("utf-8", "ignore"))
        except Exception:
            pass
    return out

def find_question_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    # also include any decoded atob insert
    decoded = decode_atob_blocks(html)
    if decoded:
        text += "\n" + "\n".join(decoded)
    return text

def sum_value_column_in_pdf(pdf_bytes: bytes, page_index: int = 1, column_name: str = "value") -> float | int:
    # page_index is 0-based (1 means page 2)
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[page_index]
        tables = page.extract_tables()
        # choose the widest table (most columns)
        best = max(tables, key=lambda t: len(t[0])) if tables else None
        if not best:
            raise ValueError("No tables found on specified PDF page.")
        df = pd.DataFrame(best[1:], columns=best[0])
        # case-insensitive match for column
        target = None
        for c in df.columns:
            if c.strip().lower() == column_name.lower():
                target = c; break
        if target is None:
            raise ValueError(f'Column "{column_name}" not found in PDF table.')
        # coerce to numeric
        s = pd.to_numeric(df[target].astype(str).str.replace(r"[^0-9\.-]", "", regex=True), errors="coerce")
        return float(s.sum())
