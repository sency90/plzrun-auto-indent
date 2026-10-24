#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plzrun-auto-indent: 터미널 vim 범위 '=' 를 파일 전체 맥락으로 정렬하는 도우미.

왜 필요한가
    vim 의 '=' 는 equalprg 가 있으면 "선택한 줄만" 그 프로그램에 넘긴다.
    astyle 은 바깥 코드를 모르니 선택 줄을 0단계 깊이부터 다시 들여써서
    전부 왼쪽 벽(0열)에 붙는다. gg=G(파일 전체)만 맞는 이유가 이것이다.

어떻게 고치나
    1) 버퍼 전체를 astyle 로 정렬한다(= gg=G 와 똑같은 결과 F).
    2) 원래 줄과 F 의 줄을 "공백을 뺀 글자 위치"로 맞춘다. astyle 은
       (이 저장소의 astylerc 기준) 공백과 줄바꿈만 바꾸므로, 공백을 뺀 글자
       흐름은 앞뒤가 같다. 단 '{' 를 앞줄에 붙일 때 그 앞의 주석 뒤로
       옮기므로(if(x) // c + '{' -> if(x) { // c) 코드 글자와 주석 글자를
       따로 센다. 빈 줄은 따로 센다.
    3) 선택 범위의 시작·끝 경계가 F 에서도 줄 경계로 남아 있으면 그 사이의
       F 줄을 그대로 가져온다(gg=G 결과를 범위만큼 잘라 붙임). 범위 안에서
       '} else {' 가 쪼개져 줄 수가 늘어도 범위 안 일이라 괜찮다.
    4) 경계가 범위 밖 줄과 합쳐져 사라진 경우(범위 첫 줄 '{' 가 범위 밖
       'if(x)' 줄에 붙는 경우 등)에는 범위 밖을 건드리지 않으려고 그 줄만
       "들여쓰기만" 고친다: 그 줄의 첫 글자가 F 에서 들어간 줄의 들여쓰기를
       쓰고, 나머지 글자는 손대지 않는다.
    범위 밖 줄은 어떤 경우에도 출력하지 않으므로 바뀔 수 없다.

사용법
    python3 plzrun_reindent.py <첫줄> <끝줄> <astyle 경로> < 버퍼 전체
    표준출력 = 첫줄~끝줄 자리에 들어갈 새 줄들. 실패하면 0 이 아닌 값으로 끝난다.

python 3.6 에서도 돌게 쓴다(회사 air-gapped Linux).
"""
import bisect
import re
import subprocess
import sys

WS = b" \t\r\n\x0b\x0c"
LEAD_WS = re.compile(rb"^[ \t]*")

# C/C++ 토큰. 코드 글자와 주석 글자를 나누는 데만 쓴다(정렬은 astyle 이 한다).
#   bc  블록 주석(안 닫혀도 끝까지)      lc  줄 주석(끝의 \ 로 다음 줄까지 이어짐)
#   raw R"d(...)d" 원시 문자열            str 문자열(안 닫히면 줄 끝까지)
#   num 숫자(1'000 의 ' 는 문자 상수가 아님)  chr 문자 상수
TOKEN = re.compile(
    rb"""
      (?P<bc>/\*.*?(?:\*/|\Z))
    | (?P<lc>//(?:\\\r?\n|[^\n])*)
    | (?P<raw>(?<![A-Za-z0-9_])(?:u8|u|U|L)?R"(?P<d>[^ ()\\\t\r\n]{0,16})\(.*?(?:\)(?P=d)"|\Z))
    | (?P<str>"(?:\\.|\\\r?\n|[^"\\\n])*"?)
    | (?P<num>\.?[0-9](?:[0-9A-Za-z_.]|'(?=[0-9A-Za-z])|[eEpP][+-])*)
    | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<chr>'(?:\\.|[^'\\\n])*'?)
    | (?P<ws>[ \t\r\x0b\x0c]+)
    | (?P<nl>\n)
    | (?P<other>.)
    """,
    re.S | re.X,
)


class Scan(object):
    """줄마다 (코드 글자 수, 주석 글자 수, 첫 글자의 종류) 를 센다."""

    def __init__(self, lines):
        n = len(lines)
        code = [0] * n
        cmt = [0] * n
        first = [None] * n          # 'k'(코드) / 'm'(주석) / None(빈 줄)
        code_s = []
        cmt_s = []
        text = b"\n".join(lines)
        line = 0
        pos = 0
        end = len(text)
        while pos < end:
            m = TOKEN.match(text, pos)
            kind = m.lastgroup
            tok = m.group(0)
            pos = m.end()
            if kind == "nl":
                line += 1
                continue
            if kind == "ws":
                continue
            if kind == "d":           # raw 의 하위 그룹 이름이 잡히는 경우 방지
                kind = "raw"
            is_cmt = kind in ("bc", "lc")
            parts = tok.split(b"\n")
            for k, part in enumerate(parts):
                if k:
                    line += 1
                body = bytes(c for c in part if c not in WS)
                if not body:
                    continue
                if is_cmt:
                    cmt[line] += len(body)
                    cmt_s.append(body)
                else:
                    code[line] += len(body)
                    code_s.append(body)
                if first[line] is None:
                    first[line] = "m" if is_cmt else "k"
        self.n = n
        self.code = code
        self.cmt = cmt
        self.first = first
        self.code_stream = b"".join(code_s)
        self.cmt_stream = b"".join(cmt_s)
        self.blank_stream = b"\0" * sum(1 for i in range(n) if not code[i] and not cmt[i])
        # 줄 i 앞 경계의 누적 위치(코드, 주석, 빈 줄). 길이 n+1.
        cs, ms, bs = [0], [0], [0]
        for i in range(n):
            cs.append(cs[-1] + code[i])
            ms.append(ms[-1] + cmt[i])
            bs.append(bs[-1] + (0 if (code[i] or cmt[i]) else 1))
        self.cs, self.ms, self.bs = cs, ms, bs

    def boundary(self, i):
        return (self.cs[i], self.ms[i], self.bs[i])


def offset_map(a, b):
    """흐름 a 의 위치 -> 흐름 b 의 위치. 둘이 같으면 그대로.
    다르면(예상 밖) 같은 앞부분·같은 뒷부분 안에서만 옮기고 나머지는 None."""
    if a == b:
        return lambda x: x
    la, lb = len(a), len(b)
    p = 0
    lim = min(la, lb)
    while p < lim and a[p] == b[p]:
        p += 1
    q = 0
    while q < lim - p and a[la - 1 - q] == b[lb - 1 - q]:
        q += 1

    def f(x):
        if x <= p:
            return x
        if x >= la - q:
            return x + (lb - la)
        return None
    return f


def split_lines(data):
    if not data:
        return []
    lines = data.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    return lines


def lead(s):
    return LEAD_WS.match(s).group(0)


def reindent(lines, first, last, formatted):
    """lines[first..last](0 기준, 끝 포함) 자리에 들어갈 줄들을 돌려준다."""
    n = len(lines)
    if first == 0 and last == n - 1:
        return formatted                      # gg=G: 지금까지와 바이트 단위로 같게
    a = Scan(lines)
    b = Scan(formatted)
    fc = offset_map(a.code_stream, b.code_stream)
    fm = offset_map(a.cmt_stream, b.cmt_stream)
    fb = offset_map(a.blank_stream, b.blank_stream)

    out_index = {}
    for j in range(b.n + 1):
        out_index[b.boundary(j)] = j

    def match(i):
        c, m, k = a.boundary(i)
        key = (fc(c), fm(m), fb(k))
        if None in key:
            return None
        return out_index.get(key)

    def fallback(i):
        """줄 i 의 들여쓰기만: 첫 글자가 F 에서 들어간 줄의 들여쓰기를 쓴다."""
        s = lines[i]
        kind = a.first[i]
        if kind is None:
            return b""
        if kind == "k":
            x = fc(a.cs[i])
            starts, widths = b.cs, b.code
        else:
            x = fm(a.ms[i])
            starts, widths = b.ms, b.cmt
        if x is None:
            return s                          # 맞출 근거가 없으면 손대지 않는다
        j = bisect.bisect_right(starts, x, 0, b.n) - 1
        while j >= 0 and widths[j] == 0:      # 같은 위치의 빈/주석 줄 건너뜀
            j -= 1
        if j < 0:
            return s
        return lead(formatted[j]) + s[len(lead(s)):]

    result = []
    i = first
    prev = match(first)                       # 직전 맞은 경계(입력 줄, 출력 줄)
    prev_i = first if prev is not None else None
    while i <= last:
        if prev_i is None:
            result.append(fallback(i))
            i += 1
            j = match(i)
            if j is not None:
                prev_i, prev = i, j
            continue
        # prev_i 부터 다음으로 맞는 경계까지를 F 에서 통째로 가져온다
        k = prev_i + 1
        j = None
        while k <= last + 1:
            j = match(k)
            if j is not None:
                break
            k += 1
        if j is None:                         # 범위 끝 경계가 안 맞음 → 남은 줄은 들여쓰기만
            for t in range(prev_i, last + 1):
                result.append(fallback(t))
            break
        result.extend(formatted[prev:j])
        prev_i, prev = k, j
        i = k
    return result


def main(argv):
    if len(argv) != 4:
        sys.stderr.write("usage: plzrun_reindent.py FIRST LAST ASTYLE < buffer\n")
        return 2
    first, last, astyle = int(argv[1]), int(argv[2]), argv[3]
    data = sys.stdin.buffer.read()
    lines = split_lines(data)
    n = len(lines)
    if n == 0:
        return 0
    first = max(1, min(first, n)) - 1
    last = max(first, min(last, n) - 1)
    src = b"\n".join(lines) + b"\n"
    try:
        p = subprocess.Popen([astyle], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        sys.stderr.write("astyle 실행 실패: %s\n" % e)
        return 3
    out, err = p.communicate(src)
    if p.returncode != 0:
        sys.stderr.write(err.decode("utf-8", "replace") or "astyle 실패\n")
        return 3
    formatted = split_lines(out)
    if not formatted:
        sys.stderr.write("astyle 출력이 비어 있음\n")
        return 3
    res = reindent(lines, first, last, formatted)
    sys.stdout.buffer.write(b"".join(s + b"\n" for s in res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
