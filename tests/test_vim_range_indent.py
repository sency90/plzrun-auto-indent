#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""터미널 vim 범위 '=' 시험 (headless vim, 임시 HOME).

    python3 tests/test_vim_range_indent.py [--corpus DIR ...] [--files N] [--seed S]

하는 일
  1) 임시 HOME 에 install.sh 를 돌린다(code CLI 는 가짜로 막아 VSCode 는 안 건드림).
     사용자의 ~/.vimrc·~/.local/bin/astyle 은 건드리지 않는다.
  2) 정해 둔 사례(동혁님 캡처 코드, 짝 안 맞는 중괄호, 문자열·주석 속 중괄호,
     라벨, namespace, } else { 쪼개짐, 범위 밖 줄과 붙는 '{' …)를 vim 으로 돌려 비교.
  3) --corpus 를 주면 그 아래 C/C++ 파일로
       - gg=G: 새 구성 == 예전 equalprg 구성 == astyle 직접 (바이트 단위)
       - 무작위 범위 V=: 범위 밖 줄 불변 + 결과를 다시 astyle 하면 원본 astyle 과 같음
       - 되살리기: 정렬된 파일의 범위 줄을 0열로 밀어 놓고 V= 하면 원래대로
     를 확인한다.
python 3.6 에서도 돈다.
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "vim"))
import plzrun_reindent as reindent  # noqa: E402

FAILS = []
COUNT = [0]


def check(name, ok, detail=""):
    COUNT[0] += 1
    if not ok:
        FAILS.append(name)
        print("FAIL %s %s" % (name, detail))


class Env(object):
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="plzrun-vimtest-")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        shim = os.path.join(self.tmp, "shim")
        os.makedirs(shim)
        with open(os.path.join(shim, "code"), "w") as f:      # VSCode CLI 막기
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(os.path.join(shim, "code"), 0o755)
        with open(os.path.join(self.home, ".vimrc"), "w") as f:
            f.write('" 사용자 줄 1\nset nocompatible\n')
        env = dict(os.environ, HOME=self.home, PATH=shim + os.pathsep + os.environ["PATH"])
        r = subprocess.run(["bash", os.path.join(REPO, "install.sh")], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            sys.stdout.write(r.stdout.decode("utf-8", "replace"))
            raise SystemExit("install.sh 실패")
        self.env = dict(os.environ, HOME=self.home)
        self.astyle = os.path.join(self.home, ".local/bin/astyle")
        vimrc = os.path.join(self.home, ".vimrc")
        self.rc_new = os.path.join(self.tmp, "rc-new.vim")
        with open(self.rc_new, "w") as f:
            f.write("source %s\nfiletype plugin indent on\n" % vimrc)
        self.rc_old = os.path.join(self.tmp, "rc-old.vim")      # 고치기 전(master) 구성
        with open(self.rc_old, "w") as f:
            f.write("set nocompatible\nautocmd FileType c,cpp setlocal equalprg=%s\n"
                    "filetype plugin indent on\n" % self.astyle)
        self.n = 0

    def astyle_text(self, text):
        r = subprocess.run([self.astyle], input=text.encode(), stdout=subprocess.PIPE,
                           env=self.env, check=True)
        return r.stdout.decode()

    def vim(self, text, cmds, rc=None, ext="cpp", ff=None):
        """text 를 파일로 열고 ex 명령들을 차례로 실행한 뒤 파일 내용을 돌려준다."""
        self.n += 1
        path = os.path.join(self.tmp, "case%d.%s" % (self.n, ext))
        with open(path, "wb") as f:
            f.write(text.encode() if ff != "dos" else text.replace("\n", "\r\n").encode())
        args = ["vim", "-Es", "-N", "-i", "NONE", "-u", rc or self.rc_new]
        for c in cmds:
            args += ["-c", c]
        args += ["-c", "wq", path]
        subprocess.run(args, env=self.env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        with open(path, "rb") as f:
            data = f.read().decode()
        return data.replace("\r\n", "\n") if ff == "dos" else data

    def vim_batch(self, text, ranges, rc=None):
        """한 vim 에서 여러 범위를 차례로: 매번 원문으로 되돌리고 V= 한 결과를 모은다."""
        self.n += 1
        src = os.path.join(self.tmp, "batch%d.cpp" % self.n)
        out = os.path.join(self.tmp, "batch%d.json" % self.n)
        spec = os.path.join(self.tmp, "batch%d.spec" % self.n)
        with open(src, "w") as f:
            f.write(text)
        with open(spec, "w") as f:
            f.write("\n".join("%d %d" % r for r in ranges) + "\n")
        script = os.path.join(self.tmp, "batch%d.vim" % self.n)
        with open(script, "w") as f:
            f.write("""
let s:orig = getline(1, '$')
let s:res = []
for s:r in readfile('%s')
  let [s:a, s:b] = split(s:r)
  silent %%delete _
  call setline(1, s:orig)
  execute 'normal ' . s:a . 'GV' . s:b . 'G='
  call add(s:res, getline(1, '$'))
endfor
call writefile([json_encode(s:res)], '%s')
""" % (spec, out))
        subprocess.run(["vim", "-Es", "-N", "-i", "NONE", "-u", rc or self.rc_new,
                        "-c", "source " + script, "-c", "qa!", src],
                       env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=600)
        with open(out) as f:
            return [("\n".join(x) + "\n") for x in json.load(f)]


def lines_b(t):
    return [x.encode() for x in lines(t)]


def lines(t):
    return t.split("\n")[:-1] if t.endswith("\n") else t.split("\n")


def outside_same(before, after, a, b):
    """1 기준 a..b 범위 밖 줄이 그대로인지(범위 줄 수는 바뀌어도 됨)."""
    x, y = lines(before), lines(after)
    tail = len(x) - b
    return x[:a - 1] == y[:a - 1] and (tail == 0 or x[-tail:] == y[-tail:]) \
        and len(y) - tail >= a - 1


def vrange(a, b):
    return "normal %dGV%dG=" % (a, b)


REPRO = """#include <cstdio>
using namespace std;
struct Info{
    int to, val;
};
char s[1005];
int v[1005][1005];
int vN[1005];
int main() {
    int n; scanf("%d", &n);
    int x;
    for(int i=0; i<n; i++) {
        scanf("%s", s);
        for(int j=i+1; j<n; j++) {
            if(j>i) {
            sscanf(s+(j<<1), "%d", &x);
            if(x) {
                v[i][vN[i]++] = {j, x};
                v[j][vN[j]++] = {i, x};
            }
            }
        }
    }

    Dfs()


    return 0;
}
"""

REPRO_FIXED_15_20 = """            if(j>i) {
                sscanf(s+(j<<1), "%d", &x);
                if(x) {
                    v[i][vN[i]++] = {j, x};
                    v[j][vN[j]++] = {i, x};
                }
"""


def restore_case(e, name, text, a, b):
    """정렬된 F 의 a..b 줄을 0열로 밀어 놓고 V= → F 로 돌아와야 한다."""
    f = e.astyle_text(text)
    fl = lines(f)
    g = fl[:a - 1] + [s.lstrip(" \t") for s in fl[a - 1:b]] + fl[b:]
    gt = "\n".join(g) + "\n"
    if e.astyle_text(gt) != f:
        print("skip %s (astyle 결과가 들여쓰기에 따라 달라짐)" % name)
        return
    got = e.vim(gt, [vrange(a, b)])
    check(name, got == f, "\n--- got\n%s--- want\n%s" % (got, f))


def builtin_cases(e):
    # 7) 동혁님 캡처 코드: 고치기 전(0열) / 고친 뒤(바깥 for 깊이)
    old = e.vim(REPRO, [vrange(15, 20)], rc=e.rc_old)
    new = e.vim(REPRO, [vrange(15, 20)])
    print("== 고치기 전(예전 equalprg) 15~20줄 V=")
    print("\n".join(lines(old)[13:21]))
    print("== 고친 뒤 15~20줄 V=")
    print("\n".join(lines(new)[13:21]))
    check("repro-before-is-col0", lines(old)[14] == "if(j>i) {")
    want = lines(REPRO)[:14] + lines(REPRO_FIXED_15_20) + lines(REPRO)[20:]
    check("repro-after", lines(new) == want, "\n" + new)

    # 1) = 연산자 여러 형태
    check("op-==", e.vim(REPRO, ["normal 16G=="]) .split("\n")[15] == " " * 16 + 'sscanf(s+(j<<1), "%d", &x);')
    got = e.vim(REPRO, ["normal 16G5=="])
    check("op-count==", "\n".join(lines(got)[15:20]) + "\n" == "".join(REPRO_FIXED_15_20.splitlines(True)[1:]))
    got = e.vim(REPRO, ["normal 16G=4j"])
    check("op-=motion", "\n".join(lines(got)[15:20]) + "\n" == "".join(REPRO_FIXED_15_20.splitlines(True)[1:]))
    got = e.vim(REPRO, ["normal 18G=i{"])
    check("op-=i{", lines(got)[17] == " " * 20 + "v[i][vN[i]++] = {j, x};" and lines(got)[16] == " " * 12 + "if(x) {",
          "\n" + got)
    got = e.vim(REPRO, ["normal 16G=ap"])
    check("op-=ap-outside", outside_same(REPRO, got, 1, 23))
    # . 반복, u 되돌리기(한 번에)
    got = e.vim(REPRO, ["normal 16G==", "normal j."])
    check("op-dot-repeat", lines(got)[16] == " " * 16 + "if(x) {", "\n" + got)
    got = e.vim(REPRO, [vrange(15, 20), "normal u"])
    check("undo-one-step", got == REPRO)
    got = e.vim(REPRO, ["exe \"normal 15G\\<C-v>20G=\""])
    check("op-ctrl-v", lines(got)[15] == " " * 16 + 'sscanf(s+(j<<1), "%d", &x);')

    # 2) gg=G 는 예전과 바이트 단위로 같게
    for nm, t in (("repro", REPRO), ("messy", MESSY)):
        a = e.vim(t, ["normal gg=G"])
        b = e.vim(t, ["normal gg=G"], rc=e.rc_old)
        check("ggG-same-" + nm, a == b == e.astyle_text(t))
        check("whole-V=-same-" + nm, e.vim(t, ["normal ggVG="]) == a)
    a = e.vim(MESSY, ["normal gg=G"], ff="dos")
    b = e.vim(MESSY, ["normal gg=G"], rc=e.rc_old, ff="dos")
    check("ggG-same-dos", a == b)

    # 4) 사례별 되살리기(범위만 0열로 밀어 놓고 V= → gg=G 결과와 같아야)
    for name, text, a, b in RESTORE:
        restore_case(e, "restore-" + name, text, a, b)

    # 5) 줄 수가 바뀌는 경우: 범위 안 } else { 는 쪼개짐(범위 밖 불변)
    t = "int f() {\n    if(a) {\n    x;\n    } else {\n    y;\n    }\n    return 0;\n}\n"
    got = e.vim(t, [vrange(3, 5)])
    want = "int f() {\n    if(a) {\n        x;\n    }\n    else {\n        y;\n    }\n    return 0;\n}\n"
    check("else-split-in-range", got == want, "\n" + got)
    # 범위 첫 줄 '{' 가 범위 밖 if(x) 에 붙어야 하는 경우: 붙이지 않고 들여쓰기만
    t = "int f() {\n    if(x)\n{\ny=1;\n}\n    return 0;\n}\n"
    got = e.vim(t, [vrange(3, 5)])
    want = "int f() {\n    if(x)\n    {\n        y=1;\n    }\n    return 0;\n}\n"
    check("attach-across-start", got == want, "\n" + got)
    # 범위 끝 if(x) 의 '{' 가 범위 밖에 있는 경우
    t = "int f() {\nif( x )\n    {\n        y=1;\n    }\n}\n"
    got = e.vim(t, [vrange(2, 2)])
    check("attach-across-end", got == "int f() {\n    if( x )\n    {\n        y=1;\n    }\n}\n", "\n" + got)
    # 범위 안에서 '{' 붙이기(범위 안 일이므로 gg=G 처럼)
    t = "int f() {\nif(x)\n{\ny=1;\n}\n}\n"
    got = e.vim(t, [vrange(2, 5)])
    check("attach-inside", got == "int f() {\n    if(x) {\n        y=1;\n    }\n}\n", "\n" + got)
    # 주석이 '{' 앞에 있어 astyle 이 글자 순서를 바꾸는 경우
    t = "int f() {\nif(x) // c\n{\ny=1;\n}\nz=2;\n}\n"
    got = e.vim(t, [vrange(6, 6)])
    check("comment-move-elsewhere", got == t.replace("\nz=2;", "\n    z=2;"), "\n" + got)
    got = e.vim(t, [vrange(3, 5)])
    check("comment-move-range", got == "int f() {\nif(x) // c\n    {\n        y=1;\n    }\nz=2;\n}\n", "\n" + got)
    # 짝 안 맞는 중괄호(닫는 쪽이 모자람)
    t = "int f() {\n    while(1) {\nif(a) {\nb;\n"
    got = e.vim(t, [vrange(3, 4)])
    check("unbalanced-open", got == "int f() {\n    while(1) {\n        if(a) {\n            b;\n", "\n" + got)
    # 짝 안 맞는 중괄호(닫는 쪽이 남음)
    t = "x;\n}\n}\nint g() {\ny;\n}\n"
    got = e.vim(t, [vrange(5, 5)])
    check("unbalanced-close", lines(got)[4] == "    y;" and outside_same(t, got, 5, 5), "\n" + got)
    # 범위 밖 줄 불변(모든 사례 공통 검사)
    for name, text, a, b in RESTORE:
        got = e.vim(text, [vrange(a, b)])
        check("outside-" + name, outside_same(text, got, a, b))
        check("content-" + name, e.astyle_text(got) == e.astyle_text(text))

    # c/cpp 가 아니면 vim 기본 '=' 그대로
    py = "def f():\n    if x:\n        y = 1\n"
    a = e.vim(py, ["set ft=python", "normal ggVG="], ext="py")
    b = e.vim(py, ["set ft=python", "normal ggVG="], ext="py", rc=e.rc_old)
    check("non-cpp-untouched", a == b)
    # astyle 이 없으면 버퍼를 그대로 두고 오류만
    got = e.vim(REPRO, ["let g:plzrun_astyle = '/nonexistent/astyle'", vrange(15, 20)])
    check("astyle-missing-no-change", got == REPRO)
    # 빈 파일, 한 줄 파일
    check("empty-file", e.vim("", ["normal gg=G"]) == "")
    check("one-line", e.vim("int a;\n", ["normal =="]) == "int a;\n")
    # 파일 끝 빈 줄 보존(gg=G 예전과 같게, 범위 = 도 끝 빈 줄 안 먹음)
    t = "int f() {\nreturn 0;\n}\n\n\n"
    a = e.vim(t, ["normal gg=G"])
    check("trailing-blank-ggG", a == e.vim(t, ["normal gg=G"], rc=e.rc_old) == e.astyle_text(t), repr(a))
    check("trailing-blank-range", e.vim(t, [vrange(2, 2)]) == t.replace("\nreturn", "\n    return"))


MESSY = """#include <cstdio>
#define SQ(x) \\
  ((x)*(x))
namespace ns {
struct A{
int a;
};
int f(int x){
const char* s = "{ not a brace";
char c = '{';
/* } block
   comment { */
// } line comment
if (x > 0)
{
switch(x){
case 1:
x++;
break;
default:
break;
}
}
else if(x<0) {
x--;
} else {
again:
x = 0;
}
#ifdef DEBUG
printf("%d\\n", x);
#endif
auto r = R"raw(
   { keep me }
)raw";
int big = 1'000'000;
return x;
}
}
"""

RESTORE = [
    ("repro-15-20", REPRO, 15, 20),
    ("repro-16-16", REPRO, 16, 16),
    ("repro-mid-start", REPRO, 17, 22),
    ("messy-namespace", MESSY, 5, 7),
    ("messy-strings", MESSY, 9, 10),
    ("messy-comments", MESSY, 13, 15),
    ("messy-switch", MESSY, 16, 22),
    ("messy-label", MESSY, 27, 29),
    ("messy-preproc", MESSY, 30, 33),
    ("messy-raw", MESSY, 33, 38),
    ("messy-after-raw", MESSY, 36, 37),
    ("messy-tail", MESSY, 36, 39),
]


def corpus_cases(e, dirs, nfiles, seed):
    files = []
    for d in dirs:
        for root, _, names in os.walk(d):
            for nm in names:
                if nm.endswith((".cpp", ".cc", ".c", ".h")):
                    p = os.path.join(root, nm)
                    if os.path.getsize(p) < 60000:
                        files.append(p)
    rnd = random.Random(seed)
    rnd.shuffle(files)
    picked = 0
    stats = {"files": 0, "ggG": 0, "ranges": 0, "content_ws_only": 0,
             "restore": 0, "restore_skip": 0}
    for p in files:
        if picked >= nfiles:
            break
        try:
            with open(p, "rb") as f:
                text = f.read().decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        text = text.replace("\r\n", "\n")
        if text.startswith("\ufeff"):        # BOM 은 vim 이 버퍼 밖에서 따로 다룬다
            text = text[1:]
        if "\r" in text or "\0" in text or not text.strip():
            continue
        if not text.endswith("\n"):
            text += "\n"
        picked += 1
        stats["files"] += 1
        n = len(lines(text))
        full = e.astyle_text(text)
        a = e.vim(text, ["normal gg=G"])
        b = e.vim(text, ["normal gg=G"], rc=e.rc_old)
        check("corpus-ggG " + p, a == b == full)
        stats["ggG"] += 1
        ranges = []
        for _ in range(6):
            x = rnd.randint(1, n)
            y = min(n, x + rnd.randint(0, 12))
            ranges.append((x, y))
        for (x, y), got in zip(ranges, e.vim_batch(text, ranges)):
            stats["ranges"] += 1
            check("corpus-outside %s %d-%d" % (p, x, y), outside_same(text, got, x, y))
            if e.astyle_text(got) == full:
                ok = True
            else:
                # 여러 줄 블록 주석의 일부만 고르면 astyle 은 주석 첫 줄 기준 상대
                # 들여쓰기를 쓰므로 다시 돌린 결과가 달라질 수 있다. 이때는 공백 말고는
                # (코드 글자·주석 글자 흐름) 아무것도 안 바뀌었는지만 본다.
                sa, sb = reindent.Scan(lines_b(text)), reindent.Scan(lines_b(got))
                ok = (sa.code_stream, sa.cmt_stream) == (sb.code_stream, sb.cmt_stream)
                stats["content_ws_only"] += 1
            check("corpus-content %s %d-%d" % (p, x, y), ok)
        # 되살리기: 정렬된 파일에서 범위 줄을 0열로 → V= → 원래대로
        fl = lines(full)
        rr = []
        gs = []
        for (x, y) in ranges:
            g = fl[:x - 1] + [s.lstrip(" \t") for s in fl[x - 1:y]] + fl[y:]
            gt = "\n".join(g) + "\n"
            if e.astyle_text(gt) != full:
                stats["restore_skip"] += 1
                continue
            rr.append((x, y))
            gs.append(gt)
        for (x, y), gt in zip(rr, gs):
            got = e.vim_batch(gt, [(x, y)])[0]
            stats["restore"] += 1
            check("corpus-restore %s %d-%d" % (p, x, y), got == full)
    print("corpus:", stats)


def install_cases(e):
    """다시 설치해도 마커 블록 하나, 제거하면 사용자 줄만 남고 도우미 폴더도 사라진다."""
    env = dict(os.environ, HOME=e.home, PATH=os.path.join(e.tmp, "shim") + os.pathsep + os.environ["PATH"])
    vimrc = os.path.join(e.home, ".vimrc")
    share = os.path.join(e.home, ".local/share/plzrun-auto-indent")
    subprocess.run(["bash", os.path.join(REPO, "install.sh")], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    with open(vimrc) as f:
        body = f.read()
    check("reinstall-one-block", body.count(">>> plzrun-auto-indent >>>") == 1 and
          body.startswith('" 사용자 줄 1\nset nocompatible\n'), body)
    check("installed-files", os.path.isfile(os.path.join(share, "plzrun-reindent.vim")) and
          os.access(os.path.join(share, "plzrun_reindent.py"), os.X_OK))
    subprocess.run(["bash", os.path.join(REPO, "uninstall.sh")], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(vimrc) as f:
        body = f.read()
    check("uninstall-vimrc", "plzrun" not in body and
          body.startswith('" 사용자 줄 1\nset nocompatible'), body)
    check("uninstall-share", not os.path.exists(share))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="append", default=[])
    ap.add_argument("--files", type=int, default=100)
    ap.add_argument("--seed", type=int, default=356)
    ap.add_argument("--keep", action="store_true")
    o = ap.parse_args()
    e = Env()
    try:
        builtin_cases(e)
        if o.corpus:
            corpus_cases(e, o.corpus, o.files, o.seed)
        install_cases(e)
    finally:
        if not o.keep:
            shutil.rmtree(e.tmp, ignore_errors=True)
        else:
            print("임시 폴더:", e.tmp)
    print("checks=%d fails=%d" % (COUNT[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
