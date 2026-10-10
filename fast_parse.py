"""Fast TSA throughput PDF parser using PyMuPDF.

Layout (MicroStrategy export):
- Each airport's hourly data is a SECTION delimited by FULL-width horizontal
  rules (x0 ~107, spanning airport->count columns). Checkpoint rows inside a
  section are separated by PARTIAL rules (x0 ~341, checkpoint->count cols).
- The airport code/name/city/state merged cell is vertically CENTERED in its
  section, so checkpoint rows can appear before AND after the header line.
  We therefore group by section (vector rules), not by text order.
- Hour blocks: sections ordered alphabetically by airport code within each
  (date, hour); a code reset marks a new hour block.
- (date, hour) per block: dense hour text markers (x < 100) assigned by
  y-range; date by walking 23->00 wraps from the manifest week_start
  (robust to DST duplicate hours).
"""
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pymupdf

CODE_FRAG_RE = re.compile(r"^[A-Z0-9]{1,3}$")
HOUR_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
NUM_RE = re.compile(r"^[\d,]+$")


def group_lines(words):
    """Group words into visual lines by vertical overlap (robust to
    PyMuPDF splitting a row into multiple (block,line) groups)."""
    ws = sorted([w for w in words if w[4].strip()], key=lambda w: w[1])
    lines = []
    cur = []
    cur_y1 = -1
    for w in ws:
        y0, y1 = w[1], w[3]
        if cur and y0 > cur_y1 - 1.0:
            lines.append(cur)
            cur = []
            cur_y1 = -1
        cur.append(w)
        cur_y1 = max(cur_y1, y1)
    if cur:
        lines.append(cur)
    out = []
    for ws2 in lines:
        ws2.sort(key=lambda w: w[0])
        yc = sum((w[1] + w[3]) / 2 for w in ws2) / len(ws2)
        out.append((yc, ws2))
    out.sort(key=lambda x: x[0])
    return out


def parse_pdf(pdf_path: Path, week_start: str, max_pages: int = 0):
    d0 = date.fromisoformat(week_start)
    doc = pymupdf.open(pdf_path)
    npages = len(doc) if not max_pages else min(max_pages, len(doc))

    sections = []  # list of dicts in document order
    cur = None  # current open section

    def close_section(pno, y):
        nonlocal cur
        if cur is not None:
            cur["y1"] = y
            # resolve airport code from fragments (codes may wrap onto 2 lines
            # in newer PDFs, e.g. 'MD'+'W' for MDW)
            frags = sorted(cur.pop("code_frags"), key=lambda t: t[0])
            concat = "".join(t for _, t in frags)
            if re.fullmatch(r"[A-Z0-9]{3}", concat):
                cur["code"] = concat
            if cur["code"]:
                sections.append(cur)
        cur = None

    for pno in range(npages):
        page = doc[pno]
        words = page.get_text("words")  # x0,y0,x1,y1,text,block,line,wordno
        line_list = group_lines(words)

        # full-width horizontal rules = section boundaries
        bounds = []
        for d in page.get_drawings():
            r = d["rect"]
            if abs(r.y1 - r.y0) < 1.0 and (r.x1 - r.x0) > 200 and r.x0 < 120:
                bounds.append(r.y0)
        bounds.sort()

        bi = 0
        for yc, ws in line_list:
            while bi < len(bounds) and bounds[bi] < yc:
                close_section(pno, bounds[bi])
                bi += 1
            if cur is None:
                cur = {"page": pno, "y0": bounds[bi - 1] if bi > 0 else 0,
                       "y1": 792.0, "code": None, "name": None, "city": None,
                       "state": None, "counts": [], "code_frags": []}
            # airport code fragments? (x 100-130; codes may wrap: 'MD'+'W')
            for w in ws:
                if 100 <= w[0] <= 130 and CODE_FRAG_RE.match(w[4]):
                    # skip the column header word "Airport"
                    if w[4] == "Airport":
                        continue
                    cur["code_frags"].append(((w[1] + w[3]) / 2, w[4]))
            # name/city/state from header line(s) (any code fragment triggers)
            for w in ws:
                if 100 <= w[0] <= 130 and CODE_FRAG_RE.match(w[4]) and w[4] != "Airport":
                    name = " ".join(w2[4] for w2 in ws if 130 <= w2[0] < 265)
                    city = " ".join(w2[4] for w2 in ws if 265 <= w2[0] < 320)
                    st = " ".join(w2[4] for w2 in ws if 320 <= w2[0] < 342)
                    cur["name"] = name
                    cur["city"] = city
                    cur["state"] = st if re.fullmatch(r"[A-Z]{2}", st) else ""
                    break
            # trailing count? (last word numeric at x0 > 400)
            if ws and NUM_RE.match(ws[-1][4]) and ws[-1][0] > 400:
                # checkpoint = words at x0 >= 340 excluding the count
                ckpt = " ".join(w2[4] for w2 in ws[:-1] if w2[0] >= 340)
                cur["counts"].append((ckpt, int(ws[-1][4].replace(",", "")), yc))
        # end of page: do NOT auto-close; a section may continue next page.
        # But consume remaining bounds (they were section ends).
        while bi < len(bounds):
            close_section(pno, bounds[bi])
            bi += 1
    close_section(npages - 1, 792.0)

    # hour markers: (page, y, hour) and date markers (page, y, date)
    markers = []
    for pno in range(npages):
        for w in doc[pno].get_text("words"):
            t = w[4].strip()
            if w[0] < 100:
                mh = HOUR_RE.match(t)
                if mh:
                    markers.append((pno, (w[1] + w[3]) / 2,
                                    f"{int(mh.group(1)):02d}:{mh.group(2)}", None))
                    continue
                md = DATE_RE.match(t)
                if md:
                    # skip page-header publication date (near title "TSA Total Throughput")
                    markers.append((pno, (w[1] + w[3]) / 2, None,
                                    f"{md.group(3)}-{int(md.group(1)):02d}-{int(md.group(2)):02d}"))
    # filter out publication-date markers: they sit above the table (y < 120)
    markers = [m for m in markers if not (m[3] and m[1] < 120)]

    # hour blocks via alphabetical code resets
    n = len(sections)
    resets = [0]
    for j in range(1, n):
        if sections[j]["code"] < sections[j - 1]["code"]:
            resets.append(j)
    nblocks = len(resets)
    blocks = []
    for b in range(nblocks):
        s = resets[b]
        e = resets[b + 1] if b + 1 < nblocks else n
        blocks.append((s, e))

    block_hour = {}
    for b, (s, e) in enumerate(blocks):
        y0 = (sections[s]["page"], sections[s]["y0"])
        le = sections[e - 1]
        y1 = (le["page"], le["y1"])
        hs = [h for (pp, yy, h, dd) in markers
              if h and (y0 <= (pp, yy) <= y1)]
        if hs:
            block_hour[b] = max(set(hs), key=hs.count)
    # interpolate missing
    known = sorted(block_hour)
    for b in range(nblocks):
        if b in block_hour:
            continue
        prev = max([k for k in known if k < b], default=None)
        nxt = min([k for k in known if k > b], default=None)
        h = None
        if prev is not None and all(x in block_hour for x in range(prev, b)):
            h = (int(block_hour[prev][:2]) + (b - prev)) % 24
        if h is None and nxt is not None:
            h = (int(block_hour[nxt][:2]) - (nxt - b)) % 24
        if h is None:
            h = b % 24
        block_hour[b] = f"{h:02d}:00"

    # dates: walk wraps from week_start
    block_date = {}
    cur_d = d0
    block_date[0] = cur_d.isoformat()
    for b in range(1, nblocks):
        hp, hc = int(block_hour[b - 1][:2]), int(block_hour[b][:2])
        if hc < hp:
            cur_d += timedelta(days=1)
        block_date[b] = cur_d.isoformat()

    # aggregate
    daily = defaultdict(int)
    names = {}
    recs = []
    for b, (s, e) in enumerate(blocks):
        d, h = block_date[b], block_hour[b]
        for j in range(s, e):
            sec = sections[j]
            code = sec["code"]
            if code not in names:
                names[code] = (sec["name"], sec["city"], sec["state"])
            for ckpt, c, yc in sec["counts"]:
                daily[(d, code)] += c
                recs.append((d, h, code, ckpt, c))
    return ([(dd, code, c) for (dd, code), c in daily.items()], names, [],
            recs)


def main():
    pdf = Path(sys.argv[1])
    week_start = sys.argv[2]
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    import time
    t0 = time.time()
    daily, names, warnings, recs = parse_pdf(pdf, week_start)
    dt = time.time() - t0
    print(f"{pdf.name}: {len(daily)} daily rows, {len(names)} airports, "
          f"{sum(c for _, _, c in daily)} total pax in {dt:.1f}s")
    if out:
        import csv
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["throughput_date", "airport_code", "throughput_count"])
            w.writerows(sorted(daily))


if __name__ == "__main__":
    main()
