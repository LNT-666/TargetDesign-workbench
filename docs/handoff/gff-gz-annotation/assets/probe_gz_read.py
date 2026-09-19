import gzip, io, os

base = os.path.dirname(os.path.abspath(__file__))
gz = os.path.join(base, "mini.gff.gz")
plain = os.path.join(base, "mini.gff")

def sniff(path):
    with open(path, "rb") as fh:
        return fh.read(2) == b"\x1f\x8b"

print("sniff plain:", sniff(plain), " sniff gz:", sniff(gz))

with io.open(plain, "r", encoding="utf-8") as fh:
    plain_text = fh.read()
with gzip.open(gz, "rt", encoding="utf-8") as fh:
    gz_text = fh.read()
print("text identical:", plain_text == gz_text, len(plain_text), len(gz_text))
print("rt newline mode translates CRLF? has_crlf:", "\r\n" in gz_text.replace("\r\n", "|CRLF|"))
print("first line:", repr(gz_text.splitlines()[0]))