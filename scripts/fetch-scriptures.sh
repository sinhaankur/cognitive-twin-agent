#!/usr/bin/env bash
# Fetch public-domain scriptures (Bhagavad Gita + Rig Veda) into VERA_HOME and
# build the on-device 'scriptures' RAG index, so Vera can quote/cite real verses
# instead of paraphrasing from the model's memory.
#
# All local + on-device after this runs; the texts are public domain and credited
# to their translators (Arnold, Griffith). Re-runnable: skips files already there.
#
#   ./scripts/fetch-scriptures.sh
set -uo pipefail

VERA_HOME="${VERA_HOME:-$HOME/Library/Application Support/Vera}"
DIR="$VERA_HOME/knowledge/scriptures"
mkdir -p "$DIR"

fetch() {  # url  dest
  local url="$1" dest="$2"
  if [ -s "$dest" ]; then echo "  have $(basename "$dest")"; return 0; fi
  echo "  fetching $(basename "$dest") ..."
  curl -sL -m 90 -o "$dest" "$url" || { echo "    failed: $url" >&2; return 1; }
  # a 404 page is tiny HTML, not the text we want
  if [ "$(wc -c < "$dest")" -lt 10000 ]; then
    echo "    too small — likely an error page, removing" >&2; rm -f "$dest"; return 1
  fi
}

echo "[scriptures] into $DIR"
# Bhagavad Gita — Edwin Arnold, Project Gutenberg #2388 (public domain)
fetch "https://www.gutenberg.org/cache/epub/2388/pg2388.txt" \
      "$DIR/bhagavad-gita-arnold.txt"
# Rig Veda — Ralph T. H. Griffith, via Internet Archive full text (public domain)
fetch "https://archive.org/download/hymnsrigveda00grifgoog/hymnsrigveda00grifgoog_djvu.txt" \
      "$DIR/rig-veda-griffith-vol1.txt"
fetch "https://archive.org/download/hymnsrigveda02grifgoog/hymnsrigveda02grifgoog_djvu.txt" \
      "$DIR/rig-veda-griffith-vol2.txt"

cat > "$DIR/SOURCES.md" <<'EOF'
# Scriptures — sources & attribution (public domain, on-device, cited)

- bhagavad-gita-arnold.txt — The Song Celestial / Bhagavad-Gîtâ, tr. Sir Edwin
  Arnold (1885). Project Gutenberg #2388. https://www.gutenberg.org/ebooks/2388
- rig-veda-griffith-vol1/2.txt — The Hymns of the Rigveda, tr. Ralph T. H.
  Griffith (1889–1896). Internet Archive full text (OCR; content intact).

Reference texts Vera may quote/cite — attributed to their translators, never
presented as her own words.
EOF

echo "[scriptures] building the 'scriptures' RAG index ..."
VERA_HOME="$VERA_HOME" PYTHONPATH="$VERA_HOME" python3 - "$DIR" <<'PY'
import sys
from cognitive_twin import rag
info = rag.build_index(sys.argv[1], name="scriptures")
print(f"  index 'scriptures' built: {info.get('chunks')} chunks")
PY

echo "[scriptures] done. Ask Vera about the Gita or the Rig Veda — she'll cite real verses."
