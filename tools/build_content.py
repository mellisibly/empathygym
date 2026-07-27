#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EmpathyGym — сборка контента веб-версии из Kotlin-источников.

Использование:
    python3 build_content.py <папка_с_kotlin> <папка_webapp>

Пример:
    python3 build_content.py ~/AndroidStudioProjects/EmpahyGym/app/src/main/java/com/example/empahygym/data ./

Что делает:
  1. TrainerData.kt  -> trainers.js          (все тренажёры, RU+EN)
  2. MarathonData.kt -> константа MD в index.html (30 дней марафона)
  3. Strings.kt      -> константа TH в index.html (8 секций теории)
  + проверки целостности. При любой ошибке файлы НЕ перезаписываются.

Правило проекта: контент правим ТОЛЬКО в Kotlin-файлах,
веб-версия всегда генерируется этим скриптом. Руками trainers.js,
MD и TH не редактировать.
"""
import json, os, re, sys


# ─────────────────────────── TrainerData.kt ───────────────────────────

def extract_listof(text, marker):
    i = text.index(marker)
    i = text.index("listOf", i)
    start = text.index("(", i)
    depth = 0; j = start; in_str = False
    while j < len(text):
        ch = text[j]
        if in_str:
            if ch == "\\": j += 2; continue
            if ch == '"': in_str = False
        else:
            if ch == '"': in_str = True
            elif ch == "(": depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0: return text[i:j + 1]
        j += 1
    raise ValueError("несбалансированные скобки")


def strip_comments(code):
    out = []; i = 0; n = len(code); in_str = False
    while i < n:
        ch = code[i]
        if in_str:
            if ch == "\\": out.append(code[i:i+2]); i += 2; continue
            out.append(ch)
            if ch == '"': in_str = False
            i += 1; continue
        if ch == '"': in_str = True; out.append(ch); i += 1; continue
        if ch == "/" and i + 1 < n and code[i+1] == "/":
            j = code.find("\n", i); i = n if j == -1 else j; continue
        out.append(ch); i += 1
    return "".join(out)


def safe_replace(code, pairs):
    result = []; i = 0; n = len(code); in_str = False; buf = []
    def flush():
        seg = "".join(buf)
        for a, b in pairs: seg = re.sub(a, b, seg)
        result.append(seg); buf.clear()
    while i < n:
        ch = code[i]
        if in_str:
            result.append(ch if ch != "\\" else code[i:i+2])
            if ch == "\\": i += 2; continue
            if ch == '"': in_str = False
            i += 1; continue
        if ch == '"': flush(); result.append(ch); in_str = True; i += 1; continue
        buf.append(ch); i += 1
    flush()
    return "".join(result)


def build_trainers(kt_path):
    kt = open(kt_path, encoding="utf-8").read()
    pairs = [
        (r"\bTrainerMode\.SINGLE\b", '"SINGLE"'), (r"\bTrainerMode\.MULTI\b", '"MULTI"'),
        (r"\bTrainerSubmode\.PICK_CORRECT\b", '"PICK_CORRECT"'),
        (r"\bTrainerSubmode\.PICK_INVALID\b", '"PICK_INVALID"'),
        (r"\btrue\b", "True"), (r"\bfalse\b", "False"), (r"\bnull\b", "None"),
    ]

    def listOf(*a): return list(a)
    def InstructionStep(text, icon=""): return text
    def TrainerOption(text, correct=False, invalid=False, valid=False, tag="", expl=""):
        o = {"t": text, "e": expl}
        if tag: o["g"] = tag
        if correct: o["ok"] = 1
        if invalid: o["inv"] = 1
        if valid: o["v"] = 1
        return o
    def TrainerCase(situation, options, mechanism=None, example=None):
        c = {"s": situation, "o": options}
        if mechanism: c["m"] = mechanism
        if example: c["ex"] = example
        return c
    def TrainerDef(id, title, desc, cases, mode, submode="PICK_CORRECT",
                   expandable=False, maxAttempts=3, conceptNote=None,
                   instructionSteps=None, allCases=None):
        sm = "m" if mode == "MULTI" else ("i" if submode == "PICK_INVALID" else "c")
        d = {"id": id, "tt": title, "ds": desc, "sm": sm,
             "ins": instructionSteps or [], "dt": allCases or []}
        if conceptNote: d["cn"] = conceptNote
        return d

    env = {"listOf": listOf, "InstructionStep": InstructionStep,
           "TrainerOption": TrainerOption, "TrainerCase": TrainerCase,
           "TrainerDef": TrainerDef}
    data = {}
    for lang, marker in (("ru", "private fun getAllRu()"), ("en", "private fun getAllEn()")):
        block = safe_replace(strip_comments(extract_listof(kt, marker)), pairs)
        data[lang] = eval(block, dict(env))

    # проверки
    assert len(data["ru"]) == len(data["en"]), "разное число тренажёров RU/EN"
    for lang in ("ru", "en"):
        for t in data[lang]:
            for ci, c in enumerate(t["dt"]):
                where = f"{lang}/{t['id']}#{ci}"
                assert c["s"].strip(), f"{where}: пустая ситуация"
                assert len(c["o"]) >= 2, f"{where}: меньше 2 вариантов"
                for o in c["o"]:
                    assert o["t"].strip() and o["e"].strip(), f"{where}: пустой текст/объяснение"
                if t["sm"] == "c":
                    assert sum(1 for o in c["o"] if o.get("ok")) == 1, f"{where}: должен быть ровно 1 correct"
                elif t["sm"] == "i":
                    assert sum(1 for o in c["o"] if o.get("inv")) == 1, f"{where}: должен быть ровно 1 invalid"
                elif t["sm"] == "m":
                    assert sum(1 for o in c["o"] if o.get("v")) >= 1, f"{where}: нет valid-вариантов"
    for t_ru, t_en in zip(data["ru"], data["en"]):
        assert t_ru["id"] == t_en["id"], f"порядок тренажёров RU/EN не совпадает: {t_ru['id']} vs {t_en['id']}"
        assert len(t_ru["dt"]) == len(t_en["dt"]), f"{t_ru['id']}: разное число кейсов RU={len(t_ru['dt'])} EN={len(t_en['dt'])}"

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    total = sum(len(t["dt"]) for t in data["ru"])
    return ("// EmpathyGym Trainer Data — автогенерация из TrainerData.kt (build_content.py)\n"
            "// НЕ редактировать вручную.\n"
            "window.TRAINER_DATA=" + payload + ";\n"), total


# ─────────────────────────── MarathonData.kt ───────────────────────────

MARA_PAT = re.compile(
    r'day = (\d+),\s*difficulty = "(\w+)",\s*context = "(\w+)",'
    r'\s*taskRu = "((?:[^"\\]|\\.)*)",\s*taskEn = "((?:[^"\\]|\\.)*)",'
    r'\s*question1Ru = "((?:[^"\\]|\\.)*)",\s*question1En = "((?:[^"\\]|\\.)*)",'
    r'\s*question2Ru = "((?:[^"\\]|\\.)*)",\s*question2En = "((?:[^"\\]|\\.)*)"')


def build_marathon(kt_path):
    kt = open(kt_path, encoding="utf-8").read()
    DF = {"easy": "ey", "medium": "md", "hard": "hd"}
    CX = {"friends": "fr", "self": "sl", "colleagues": "cl", "partner": "pt", "all": "al"}
    unesc = lambda s: s.replace('\\"', '"').replace("\\n", "\n")
    ru, en = [], []
    for d in MARA_PAT.findall(kt):
        day, diff, ctx, tru, ten, q1r, q1e, q2r, q2e = d
        base = {"d": int(day), "df": DF[diff], "cx": CX[ctx]}
        ru.append({**base, "tk": unesc(tru), "q1": unesc(q1r), "q2": unesc(q2r)})
        en.append({**base, "tk": unesc(ten), "q1": unesc(q1e), "q2": unesc(q2e)})
    assert len(ru) == 30, f"марафон: найдено {len(ru)} дней вместо 30"
    return "const MD=" + json.dumps({"ru": ru, "en": en}, ensure_ascii=False, separators=(",", ":")) + ";\n"


# ─────────────────────────── Strings.kt (теория) ───────────────────────────

TH_PAT = re.compile(
    r'TheorySection\(\s*title\s*=\s*"((?:[^"\\]|\\.)*)"\s*,\s*body\s*=\s*"""(.*?)"""\s*\)', re.S)


def build_theory(kt_path):
    kt = open(kt_path, encoding="utf-8").read()
    ru_i, en_i = kt.index("val ru = AppStrings"), kt.index("val en = AppStrings")
    def parse(block):
        return [{"t": m.group(1), "b": m.group(2)} for m in TH_PAT.finditer(block)]
    ru, en = parse(kt[ru_i:en_i]), parse(kt[en_i:])
    assert len(ru) == len(en) and len(ru) > 0, f"теория: секций RU={len(ru)} EN={len(en)}"
    return "const TH=" + json.dumps({"ru": ru, "en": en}, ensure_ascii=False, separators=(",", ":")) + ";", len(ru)


# ─────────────────────────── main ───────────────────────────

def main():
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(1)
    kt_dir, web_dir = sys.argv[1], sys.argv[2]
    p = lambda *a: os.path.join(*a)

    trainers_js, n_cases = build_trainers(p(kt_dir, "TrainerData.kt"))
    md_js = build_marathon(p(kt_dir, "MarathonData.kt"))
    th_js, n_sec = build_theory(p(kt_dir, "Strings.kt"))

    html_path = p(web_dir, "index.html")
    html = open(html_path, encoding="utf-8").read()
    html, n1 = re.subn(r"const MD=\{.*?\};\n", lambda m: md_js, html, count=1, flags=re.S)
    html, n2 = re.subn(r"const TH=\{.*?\};\n", lambda m: th_js + "\n", html, count=1, flags=re.S)
    assert n1 == 1 and n2 == 1, "не нашла константы MD/TH в index.html"

    open(p(web_dir, "trainers.js"), "w", encoding="utf-8").write(trainers_js)
    open(html_path, "w", encoding="utf-8").write(html)
    print(f"✓ trainers.js: {n_cases} кейсов на язык")
    print(f"✓ index.html: марафон 30 дней, теория {n_sec} секций")
    print("Готово. Не забудьте поднять версию кеша в sw.js (empathygym-vN → vN+1).")


if __name__ == "__main__":
    main()
