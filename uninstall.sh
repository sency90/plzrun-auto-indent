#!/usr/bin/env bash
# ============================================================================
#  plzrun-auto-indent uninstaller
#  - install.sh 가 생성/변경한 것만 정확히 되돌림 (사용자 다른 설정은 보존)
#    1) ~/.local/bin/astyle  (우리가 빌드·설치한 것)
#    2) ~/.astylerc          (우리 마커가 있을 때만)
#    3) ~/.vimrc 의 마커 블록 (>>> plzrun-auto-indent >>> ~ <<<)
#    4) VSCode settings.json 에서 우리가 넣은 키만 제거
#    5) VSCode 확장 jkillian.custom-local-formatters 제거
#  사용법:  bash uninstall.sh
# ============================================================================
set -uo pipefail   # (set -e 미사용: 일부가 없어도 끝까지 정리)

log()  { printf '\033[1;32m[plzrun]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plzrun:warn]\033[0m %s\n' "$*"; }

OS="$(uname -s)"
EXT_ID="jkillian.custom-local-formatters"
ASTYLE_DEST="$HOME/.local/bin/astyle"

# --- 1) astyle 바이너리 제거 (우리가 만든 Artistic Style 인지 확인 후) ---
if [ -f "$ASTYLE_DEST" ]; then
    if "$ASTYLE_DEST" --version 2>/dev/null | grep -qi "Artistic Style"; then
        rm -f "$ASTYLE_DEST"; log "제거: $ASTYLE_DEST"
        # 우리가 만든 빈 ~/.local/bin 이면 정리 (다른 파일 있으면 유지)
        rmdir "$HOME/.local/bin" 2>/dev/null && log "빈 ~/.local/bin 제거" || true
    else
        warn "$ASTYLE_DEST 가 우리가 만든 astyle 이 아님 → 보존"
    fi
else
    log "astyle 바이너리 없음 (건너뜀)"
fi

# --- 2) ~/.astylerc 제거 (우리 마커 헤더가 있을 때만) ---
ASTYLERC="$HOME/.astylerc"
if [ -f "$ASTYLERC" ] && grep -q "동혁님 C/C++ 코드 스타일 (AStyle)" "$ASTYLERC"; then
    rm -f "$ASTYLERC"; log "제거: $ASTYLERC"
elif [ -f "$ASTYLERC" ]; then
    warn "$ASTYLERC 가 우리 것이 아님(마커 없음) → 보존"
else
    log "~/.astylerc 없음 (건너뜀)"
fi

# --- 3) ~/.vimrc 마커 블록 제거 ---
VIMRC="$HOME/.vimrc"
if [ -f "$VIMRC" ] && grep -q "plzrun-auto-indent" "$VIMRC"; then
    python3 - "$VIMRC" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p).read()
# 마커 블록(앞의 빈 줄 포함) 제거
s2 = re.sub(r'\n*^".*>>> plzrun-auto-indent >>>.*?^".*<<< plzrun-auto-indent <<<.*?$\n?',
            '\n', s, flags=re.S | re.M)
open(p, "w").write(s2)
PY
    log "~/.vimrc 마커 블록 제거"
else
    log "~/.vimrc 마커 없음 (건너뜀)"
fi

# --- 4) VSCode settings.json 에서 우리 키만 제거 ---
# install.sh 와 동일하게 Remote-WSL 의 Windows User 설정 경로도 탐지(거기에도 썼으므로 제거 대상)
WIN_USER_SETTINGS=""
if [ "$OS" = "Linux" ] && grep -qiE 'microsoft|wsl' /proc/sys/kernel/osrelease 2>/dev/null; then
    if command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
        _appdata="$(cd /mnt/c 2>/dev/null && cmd.exe /c 'echo %APPDATA%' 2>/dev/null | tr -d '\r')"
        [ -n "$_appdata" ] && WIN_USER_SETTINGS="$(wslpath -u "$_appdata" 2>/dev/null)/Code/User/settings.json"
    fi
fi

OS="$OS" WIN_USER_SETTINGS="$WIN_USER_SETTINGS" python3 - <<'PY'
import json, os, re
osname = os.environ["OS"]

# VSCode settings.json 은 JSONC → 주석/후행쉼표 제거 후 파싱(엄격 파서 오판 방지)
def loads_jsonc(text):
    out = []; i = 0; n = len(text); in_str = False; esc = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': in_str = False
            i += 1; continue
        if c == '"':
            in_str = True; out.append(c); i += 1; continue
        if c == "/" and i + 1 < n and text[i+1] == "/":
            while i < n and text[i] != "\n": i += 1
            continue
        if c == "/" and i + 1 < n and text[i+1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i+1] == "/"): i += 1
            i += 2; continue
        out.append(c); i += 1
    s = "".join(out)
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    return json.loads(s)

targets = []
if osname == "Darwin":
    targets.append(os.path.expanduser("~/Library/Application Support/Code/User/settings.json"))
else:
    targets.append(os.path.expanduser("~/.config/Code/User/settings.json"))
    targets.append(os.path.expanduser("~/.vscode-server/data/Machine/settings.json"))
    _win = os.environ.get("WIN_USER_SETTINGS", "")
    if _win:
        targets.append(_win)

OURFMT = "jkillian.custom-local-formatters"
GLOBAL_KEYS = ["editor.autoIndent"]
BACKUP = os.path.expanduser("~/.config/plzrun-auto-indent/orig-settings.json")
backup = {}
if os.path.exists(BACKUP):
    try: backup = json.loads(open(BACKUP).read() or "{}")
    except Exception: backup = {}
for p in targets:
    if not os.path.exists(p):
        continue
    try:
        t = open(p).read().strip(); cfg = loads_jsonc(t) if t else {}
    except Exception as e:
        print(f"  ! {p} 파싱 실패 → 건너뜀(원본 보존) ({e})"); continue
    changed = False
    # 우리가 넣은 astyle 포매터 등록 제거
    if "customLocalFormatters.formatters" in cfg:
        cfg.pop("customLocalFormatters.formatters", None); changed = True
    # 전역 공통키: 백업된 원래값으로 복원 (없었으면 제거)
    b = backup.get(p, {})
    for k in GLOBAL_KEYS:
        info = b.get(k)
        if info is not None:           # 백업 있음 → 정확히 복원
            if info.get("had"):
                cfg[k] = info.get("val"); changed = True
            else:
                if k in cfg: cfg.pop(k, None); changed = True
        else:                          # 백업 없음 → 우리 값일 때만 제거(best-effort)
            if cfg.get(k) == "keep":
                cfg.pop(k, None); changed = True
    # VSCodeVim o/O 리맵: 우리가 넣은 항목만 제거 (구/신 버전 모두). 사용자 다른 리맵은 보존.
    OUR_CMDS = (["plzrun.fixIndent"], ["editor.action.reindentselectedlines"])
    def _is_ours(e):
        return (isinstance(e, dict)
                and e.get("before") in (["o"], ["O"])
                and e.get("after") == e.get("before")
                and e.get("commands") in OUR_CMDS)
    arr = cfg.get("vim.normalModeKeyBindingsNonRecursive")
    if isinstance(arr, list):
        new = [e for e in arr if not _is_ours(e)]
        if len(new) != len(arr):
            changed = True
            if new:
                cfg["vim.normalModeKeyBindingsNonRecursive"] = new
            else:
                cfg.pop("vim.normalModeKeyBindingsNonRecursive", None)
    # visual 모드 '=' 리맵(우리 것)만 제거
    def _is_ours_v(e):
        return (isinstance(e, dict) and e.get("before") == ["="]
                and e.get("commands") == ["plzrun.reindentSelection"])
    varr = cfg.get("vim.visualModeKeyBindingsNonRecursive")
    if isinstance(varr, list):
        vnew = [e for e in varr if not _is_ours_v(e)]
        if len(vnew) != len(varr):
            changed = True
            if vnew:
                cfg["vim.visualModeKeyBindingsNonRecursive"] = vnew
            else:
                cfg.pop("vim.visualModeKeyBindingsNonRecursive", None)
    for lang in ("[cpp]", "[c]"):
        o = cfg.get(lang)
        if isinstance(o, dict) and o.get("editor.defaultFormatter") == OURFMT:
            o.pop("editor.defaultFormatter", None); changed = True
            if o:
                cfg[lang] = o
            else:
                cfg.pop(lang, None)
    for lang in ("[makefile]", "[go]"):
        if cfg.get(lang) == {"editor.insertSpaces": False, "editor.detectIndentation": False}:
            cfg.pop(lang); changed = True
    fa = cfg.get("files.associations")
    if isinstance(fa, dict):
        for k, v in (("*.mak","makefile"), ("*.mk","makefile"), ("GNUmakefile","makefile")):
            if fa.get(k) == v:
                fa.pop(k); changed = True
        if fa == {}:
            cfg.pop("files.associations", None)
    if changed:
        with open(p, "w") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False); f.write("\n")
        print(f"  VSCode 설정에서 우리 키 제거: {p}")
PY
log "VSCode settings 정리 완료"

# 원래값 백업 파일 정리 (복원 끝났으니 제거)
rm -f "$HOME/.config/plzrun-auto-indent/orig-settings.json"
rmdir "$HOME/.config/plzrun-auto-indent" 2>/dev/null || true

# --- 5) VSCode 확장 제거 (우리가 설치한 것들) ---
if command -v code >/dev/null 2>&1; then
    for X in "$EXT_ID" "plzrun.plzrun-vim-indent"; do
        if code --uninstall-extension "$X" >/dev/null 2>&1; then
            log "VSCode 확장 제거: $X"
        else
            warn "확장 제거 실패(미설치일 수 있음): $X"
        fi
    done
else
    warn "'code' CLI 없음 → 확장 수동 제거 필요(원하면): $EXT_ID, plzrun.plzrun-vim-indent"
fi

echo
log "✅ 제거 완료! (VSCode는 Reload Window, 터미널 vim은 재실행하면 반영)"
