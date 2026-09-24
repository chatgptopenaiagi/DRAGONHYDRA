"""Extraction quality is distinct from an explicit, scoped terms review."""
import io
import re
import sys
from .provenance import digest
from .contracts import utcnow


def readable_english(text):
    if not isinstance(text,str) or len(text.strip()) < 200 or '\ufffd' in text:
        return False
    if any(ord(c)<32 and c not in '\n\r\t' for c in text):
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters or sum(c.isascii() for c in letters)/len(letters) < 0.97:
        return False
    words = re.findall(r'[a-z]+',text.lower())
    return len(words)>=40 and len(set(words)&{'the','data','user','service','agreement','terms','research'})>=5


def evidence_record(content, text, source_url, retrieved_at, method, *, reviewed=False, review_note=None):
    reliable = readable_english(text)
    # Text passing a heuristic alone is NEVER legal approval. Independent review required.
    verified = reliable and reviewed is True and bool(review_note) and method.startswith('pypdf/6.19.0')
    return {'SOURCE_URL':source_url,'RETRIEVED_AT':retrieved_at,'CONTENT_HASH':digest(content),
            'EXTRACTION_METHOD':method,'EXTRACTION_STATUS':'READABLE' if reliable else 'UNRELIABLE',
            'EXTRACTED_TEXT_HASH':digest(text.encode()) if isinstance(text,str) else None,
            'TERMS_STATUS':'VERIFIED' if verified else 'UNVERIFIED',
            'LICENSE_STATUS':'VERIFIED' if verified else 'UNVERIFIED',
            'REVIEW_NOTE':review_note if verified else None,'REVIEWED_AT':utcnow() if verified else None}


def extract_pdf(content, root):
    if len(content)>2_000_000:
        return '', 'pypdf/6.19.0:SIZE_REJECTED'
    vendor = root/'runtime/vendor/pypdf-6.19.0'
    if str(vendor) not in sys.path:
        sys.path.insert(0,str(vendor))
    import pypdf
    from pathlib import Path
    if pypdf.__version__!='6.19.0' or not Path(pypdf.__file__).resolve().is_relative_to(vendor.resolve()):
        raise RuntimeError('Unpinned PDF parser')
    try:
        reader = pypdf.PdfReader(io.BytesIO(content),strict=True)
        if reader.is_encrypted or len(reader.pages)>20:
            return '', 'pypdf/6.19.0:UNSUPPORTED'
        return '\n'.join(p.extract_text() or '' for p in reader.pages), 'pypdf/6.19.0'
    except Exception:
        return '', 'pypdf/6.19.0:EXTRACTION_FAILED'
