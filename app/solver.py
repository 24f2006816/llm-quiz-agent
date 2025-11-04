import re, time, asyncio, pandas as pd
from urllib.parse import urlparse
from app.scraper import fetch_quiz_page_html
from app.utils import (
    extract_submit_url, extract_download_links, http_get_bytes,
    http_post_json, find_question_text, sum_value_column_in_pdf, decode_atob_blocks
)

async def solve_single(url: str, email: str, secret: str) -> dict:
    html = await fetch_quiz_page_html(url)
    submit_url = extract_submit_url(html)
    if not submit_url:
        # sometimes in decoded atob text
        for decoded in decode_atob_blocks(html):
            submit_url = extract_submit_url(decoded) or submit_url
    if not submit_url:
        raise ValueError("Submit URL not found on quiz page.")

    qtext = find_question_text(html)
    # Heuristics for known sample pattern:
    # "Download file ... What is the sum of the “value” column in the table on page 2?"
    answer = None

    # 1) If PDF mentioned with "table on page 2"
    if re.search(r'\btable on page\s*2\b', qtext, re.I) and "value" in qtext.lower():
        links = extract_download_links(html)
        # pick first PDF link
        pdf_links = [u for u in links if urlparse(u).path.lower().endswith(".pdf")]
        if not pdf_links:
            # maybe inside decoded atob block
            for decoded in decode_atob_blocks(html):
                pdf_links += [u for u in re.findall(r'https?://[^\s"<>]+', decoded) if u.lower().endswith(".pdf")]
        if not pdf_links:
            raise ValueError("PDF link not found.")
        pdf_bytes = await http_get_bytes(pdf_links[0])
        val = sum_value_column_in_pdf(pdf_bytes, page_index=1, column_name="value")
        # numeric answer
        answer = val

    # 2) Fallbacks: CSV/Excel sum, count, etc., based on hints
    if answer is None:
        links = extract_download_links(html)
        data_link = None
        for u in links:
            p = urlparse(u).path.lower()
            if p.endswith(".csv") or p.endswith(".xlsx") or p.endswith(".xls"):
                data_link = u; break
        if data_link:
            b = await http_get_bytes(data_link)
            if data_link.lower().endswith(".csv"):
                df = pd.read_csv(pd.io.common.BytesIO(b))
            else:
                df = pd.read_excel(pd.io.common.BytesIO(b))
            # naive default: sum of 'value' if present, else first numeric column
            target = None
            for c in df.columns:
                if str(c).strip().lower() == "value":
                    target = c; break
            if target is None:
                for c in df.columns:
                    if pd.api.types.is_numeric_dtype(df[c]):
                        target = c; break
            if target is None:
                raise ValueError("No numeric columns found to aggregate.")
            answer = float(df[target].fillna(0).sum())

    # 3) If still no answer, just echo text (debug)
    if answer is None:
        answer = "unhandled_question"

    payload = {
        "email": email,
        "secret": secret,
        "url": url,
        "answer": answer
    }
    result = await http_post_json(submit_url, payload)
    return {"question": qtext[:280], "submitted_to": submit_url, "answer": answer, "result": result}

async def solve_quiz_chain(start_url: str, email: str, secret: str) -> list[dict]:
    t0 = time.time()
    url = start_url
    out = []
    while url and (time.time() - t0) < 180:
        res = await solve_single(url, email, secret)
        out.append(res)
        nxt = res.get("result", {}).get("url")
        # If incorrect and a new url is provided, prefer the new one
        url = nxt
    return out
