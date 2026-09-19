import re, io
p = r"R:\songji\论文\3\ALLEGRO-2025-nar.txt"
d = io.open(p, encoding="utf-8").read()
m = re.search(r"Abstract\n(.*?)\n\s*\n", d, re.S)
a = m.group(1)
print("abstract_words", len(re.findall(r"[A-Za-z][A-Za-z-]*", a)))
nums = [int(x) for x in re.findall(r"^\[\s*(\d+)\s*\]", d, re.M)]
print("bracket_refs_max", max(nums) if nums else 0)
print("ref_list_tail", nums[-8:] if nums else [])
print("fig_refs", len(re.findall(r"Fig(?:ure|\.)\s*\d+", d)))
print("main_fig_labels", sorted(set(int(x) for x in re.findall(r"^Figure\s+(\d+)\.", d, re.M))))
print("table_refs", len(re.findall(r"Table\s*S?\d+", d)))
print("supp_fig_refs", len(re.findall(r"Supplementary Fig", d)))
print("graphical_abstract", "Graphical abstract" in d)
print("doi", re.search(r"https://doi.org/\S+", d).group(0))
for key in ["Data availability", "Supplementary data", "Conflict of interest", "Funding", "Acknowledgements"]:
    idx = [i for i in range(len(d)) if d.startswith(key, i)]
    print(key, "occurrences", len(idx), "first_at", idx[0] if idx else None)
print("---- data availability block ----")
i = d.rindex("Data availability")
print(d[i:i+520])