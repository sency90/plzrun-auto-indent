#!/usr/bin/env bash
# ============================================================================
#  plzrun-auto-indent installer  (self-contained / air-gapped 가능)
#  - astyle 를 외부 패키지매니저 없이 repo 동봉 소스에서 g++ 로 직접 빌드
#  - 정렬 규칙(~/.astylerc) + 터미널 vim(equalprg) + VSCode(설정·확장) 자동 구성
#
#  설계 원칙: "요구사항 검사 → 임시 빌드 성공 → 그 다음에야 실제 설치"
#             (요구사항 미충족 시 시스템을 전혀 건드리지 않고 중단)
#  사용법:  bash install.sh
# ============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { printf '\033[1;32m[plzrun]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[plzrun:warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[plzrun:err]\033[0m %s\n' "$*" >&2; exit 1; }

OS="$(uname -s)"
EXT_ID="jkillian.custom-local-formatters"
ASTYLE_SRC="$SCRIPT_DIR/vendor/astyle-3.6.16/src"
ASTYLE_DEST="$HOME/.local/bin/astyle"     # 빌드 결과 설치 위치 (우리가 생성)
MIN_GCC_MAJOR=8                            # astyle 3.6.16 = C++17(std::filesystem)
MIN_PY="3.6"                               # install 스크립트의 settings 병합용

# ============================================================================
#  STEP 0. 요구사항 검사 (이 단계에서는 시스템을 절대 변경하지 않음)
# ============================================================================
log "요구사항 검사 중..."

# --- 0-1. 동봉 소스 존재 ---
[ -d "$ASTYLE_SRC" ] || die "astyle 소스가 없습니다: $ASTYLE_SRC (repo가 손상됨)"

# --- 0-2. g++ 존재 ---
command -v g++ >/dev/null 2>&1 || die "g++ 가 없습니다. C/C++ 컴파일러(g++)를 먼저 설치하세요."

# --- 0-3. g++ 버전 (gcc면 major>=8 / clang이면 통과, 빌드테스트로 최종확인) ---
if g++ --version 2>/dev/null | grep -qi clang; then
    log "컴파일러: clang ($(g++ --version | head -1)) — C++17 지원 가정"
else
    GCC_VER="$(g++ -dumpfullversion 2>/dev/null || g++ -dumpversion 2>/dev/null || echo 0)"
    GCC_MAJOR="${GCC_VER%%.*}"
    case "$GCC_MAJOR" in (''|*[!0-9]*) GCC_MAJOR=0;; esac
    if [ "$GCC_MAJOR" -lt "$MIN_GCC_MAJOR" ]; then
        die "g++ $GCC_VER 감지 — astyle 3.6.16 빌드에는 g++ ${MIN_GCC_MAJOR}+ (C++17/std::filesystem) 가 필요합니다. 설치를 중단합니다."
    fi
    log "컴파일러: g++ $GCC_VER (OK)"
fi

# --- 0-4. python3 존재 + 버전 (settings.json 병합용) ---
command -v python3 >/dev/null 2>&1 || die "python3 가 없습니다 (VSCode 설정 병합에 필요). 설치 후 다시 실행하세요."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,6) else 1)' \
    || die "python3 ${MIN_PY}+ 가 필요합니다. 현재: $(python3 --version 2>&1)"
log "python3: $(python3 --version 2>&1) (OK)"

# ============================================================================
#  STEP 1. astyle 임시 빌드 (성공해야만 다음 단계로 — 실패 시 시스템 변경 0)
# ============================================================================
TMPDIR_BUILD="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_BUILD"' EXIT
TMP_BIN="$TMPDIR_BUILD/astyle"
BUILD_LOG="$TMPDIR_BUILD/build.log"

log "astyle 3.6.16 빌드 중 (g++, C++17)..."
build_ok=0
# (1) 추가 라이브러리 없이  (g++ 11+, clang)
if g++ -O2 -std=c++17 "$ASTYLE_SRC"/*.cpp -o "$TMP_BIN" >"$BUILD_LOG" 2>&1; then
    build_ok=1
# (2) std::filesystem 분리 라이브러리 링크  (g++ 8~10)
elif [ "$OS" = "Linux" ] && g++ -O2 -std=c++17 "$ASTYLE_SRC"/*.cpp -o "$TMP_BIN" -lstdc++fs >>"$BUILD_LOG" 2>&1; then
    build_ok=1
fi
[ "$build_ok" = "1" ] || { echo "----- build.log -----"; cat "$BUILD_LOG"; die "astyle 빌드 실패. 위 로그 확인. (시스템은 변경되지 않았습니다.)"; }

# 빌드 산출물 동작 검증
"$TMP_BIN" --version >/dev/null 2>&1 || die "빌드된 astyle 이 실행되지 않습니다. (시스템은 변경되지 않았습니다.)"
log "빌드 성공: $("$TMP_BIN" --version)"

# ============================================================================
#  여기서부터 실제 설치 (모든 검사·빌드 통과 후에만 진행)
# ============================================================================

# --- 2. astyle 바이너리 설치 ---
mkdir -p "$(dirname "$ASTYLE_DEST")"
install -m 0755 "$TMP_BIN" "$ASTYLE_DEST"
log "astyle 설치: $ASTYLE_DEST"

# --- 3. ~/.astylerc (정렬 규칙) ---
cp "$SCRIPT_DIR/astylerc" "$HOME/.astylerc"
log "~/.astylerc 설치 완료"

# --- 4. ~/.vimrc 패치 (터미널 vim gg=G → astyle 절대경로) ---
#     기존 마커 블록이 있으면 제거 후 최신 경로로 다시 기록 (idempotent + 경로 갱신)
VIMRC="$HOME/.vimrc"
if [ -f "$VIMRC" ] && grep -q "plzrun-auto-indent" "$VIMRC"; then
    VIMRC="$VIMRC" python3 - <<'PY'
import os, re
p = os.environ["VIMRC"]; s = open(p).read()
s = re.sub(r'\n*^".*>>> plzrun-auto-indent >>>.*?<<< plzrun-auto-indent <<<.*?$\n?',
           '\n', s, flags=re.S | re.M)
open(p, "w").write(s)
PY
fi
{
    echo ""
    echo "\" >>> plzrun-auto-indent >>>"
    echo "\" C/C++: gg=G 를 astyle(~/.astylerc 규칙)로 정렬"
    echo "autocmd FileType c,cpp setlocal equalprg=$ASTYLE_DEST"
    echo "\" Makefile/Go: 탭 필수 → 전역 expandtab 무시"
    echo "autocmd FileType make,go setlocal noexpandtab"
    echo "\" <<< plzrun-auto-indent <<<"
} >> "$VIMRC"
log "~/.vimrc 패치 완료 (equalprg=$ASTYLE_DEST)"

# --- 5. VSCode 전역 settings.json 병합 (기존 설정 보존) ---
# Remote-WSL 대응: WSL 안에서 돌면 VSCode(원격)가 실제로 읽는 User 설정은
#   Windows 쪽(%APPDATA%\Code\User\settings.json)에 있다. 그 경로를 cmd.exe+wslpath 로
#   찾아내 병합 대상에 추가한다. (WSL 안 ~/.config/Code/User 는 네이티브 GUI 전용이라 안 읽힘)
WIN_USER_SETTINGS=""
if [ "$OS" = "Linux" ] && grep -qiE 'microsoft|wsl' /proc/sys/kernel/osrelease 2>/dev/null; then
    if command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
        _appdata="$(cd /mnt/c 2>/dev/null && cmd.exe /c 'echo %APPDATA%' 2>/dev/null | tr -d '\r')"
        if [ -n "$_appdata" ]; then
            _winuser="$(wslpath -u "$_appdata" 2>/dev/null)/Code/User/settings.json"
            # /mnt/c 가 실제로 마운트돼 접근 가능할 때만 채택
            if [ -d "$(dirname "$(dirname "$_winuser")")" ] || [ -d "/mnt/c" ]; then
                WIN_USER_SETTINGS="$_winuser"
                log "Remote-WSL 감지 → Windows User 설정도 병합: $WIN_USER_SETTINGS"
            fi
        fi
    fi
    [ -z "$WIN_USER_SETTINGS" ] && warn "WSL이지만 Windows User 설정 경로를 못 찾음 → WSL 쪽만 병합(키 연결이 회사 VSCode에 안 먹으면 수동 추가 필요)."
fi

ASTYLE_DEST="$ASTYLE_DEST" OS="$OS" WIN_USER_SETTINGS="$WIN_USER_SETTINGS" python3 - <<'PY'
import json, os
astyle = os.environ["ASTYLE_DEST"]; osname = os.environ["OS"]
OURFMT = "jkillian.custom-local-formatters"
# 전역 공통키(우리가 덮어쓰는 것)의 원래값을 기록 → uninstall이 정확히 복원
BACKUP = os.path.expanduser("~/.config/plzrun-auto-indent/orig-settings.json")
backup = {}
if os.path.exists(BACKUP):
    try: backup = json.loads(open(BACKUP).read() or "{}")
    except Exception: backup = {}
GLOBAL_KEYS = ["editor.autoIndent"]   # 전역(all languages) 적용 키

targets = []
if osname == "Darwin":
    targets.append(os.path.expanduser("~/Library/Application Support/Code/User/settings.json"))
else:
    targets.append(os.path.expanduser("~/.config/Code/User/settings.json"))
    if os.path.isdir(os.path.expanduser("~/.vscode-server")):
        targets.append(os.path.expanduser("~/.vscode-server/data/Machine/settings.json"))
    # Remote-WSL: Windows 쪽 User 설정(VSCode 원격이 실제로 읽는 곳)
    _win = os.environ.get("WIN_USER_SETTINGS", "")
    if _win:
        targets.append(_win)
for p in targets:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    cfg = {}
    if os.path.exists(p):
        try:
            t = open(p).read().strip(); cfg = json.loads(t) if t else {}
        except Exception as e:
            os.rename(p, p + ".plzrun.bak")
            print(f"  ! settings.json 파싱 실패 → {p}.plzrun.bak 백업 후 재작성 ({e})")
            cfg = {}
    # 원래값 백업 (최초 1회만 — 재설치로 'keep'이 원래값으로 덮이지 않게)
    if p not in backup:
        backup[p] = {k: ({"had": True, "val": cfg[k]} if k in cfg else {"had": False}) for k in GLOBAL_KEYS}
    cfg["customLocalFormatters.formatters"] = [{"command": astyle, "languages": ["cpp", "c"]}]
    # [cpp]/[c]: 덮어쓰지 않고 우리 키(defaultFormatter)만 병합
    for _lang in ("[cpp]", "[c]"):
        _o = cfg[_lang] if isinstance(cfg.get(_lang), dict) else {}
        _o["editor.defaultFormatter"] = OURFMT
        cfg[_lang] = _o
    # 전역(all languages): '{' 사이 Enter 자동 펼침 끔 → 개행 1개 (vim 손버릇 호환)
    cfg["editor.autoIndent"] = "keep"
    # VSCodeVim: o/O 가 native 동작(줄 열기+입력모드) 후 plzrun.fixIndent(전용 확장)로
    #   브래킷 깊이 기반 들여쓰기. reindent 와 달리 '빈 줄 위가 빈 줄'이어도 정확. 배열엔 우리 항목만 append.
    OUR_VIM = [
        {"before": ["o"], "after": ["o"], "commands": ["plzrun.fixIndent"]},
        {"before": ["O"], "after": ["O"], "commands": ["plzrun.fixIndent"]},
    ]
    _arr = cfg.get("vim.normalModeKeyBindingsNonRecursive")
    if not isinstance(_arr, list): _arr = []
    for _e in OUR_VIM:
        if _e not in _arr: _arr.append(_e)
    cfg["vim.normalModeKeyBindingsNonRecursive"] = _arr
    # visual 모드 '=' : 선택 영역을 바깥 맥락 유지하며 재들여쓰기 (vim '=' 처럼)
    OUR_VVIM = [{"before": ["="], "commands": ["plzrun.reindentSelection"]}]
    _varr = cfg.get("vim.visualModeKeyBindingsNonRecursive")
    if not isinstance(_varr, list): _varr = []
    for _e in OUR_VVIM:
        if _e not in _varr: _varr.append(_e)
    cfg["vim.visualModeKeyBindingsNonRecursive"] = _varr
    cfg["[makefile]"] = {"editor.insertSpaces": False, "editor.detectIndentation": False}
    cfg["[go]"]       = {"editor.insertSpaces": False, "editor.detectIndentation": False}
    fa = cfg.get("files.associations", {}) or {}
    fa.update({"*.mak": "makefile", "*.mk": "makefile", "GNUmakefile": "makefile"})
    cfg["files.associations"] = fa
    with open(p, "w") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False); f.write("\n")
    print(f"  VSCode 설정 병합: {p}")
os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
open(BACKUP, "w").write(json.dumps(backup, ensure_ascii=False, indent=2))
PY
log "VSCode 전역 settings.json 병합 완료"

# --- 6. VSCode 확장 자동 설치 (astyle 포매터 다리) ---
if command -v code >/dev/null 2>&1; then
    if code --install-extension "$EXT_ID" --force >/dev/null 2>&1; then
        log "VSCode 확장 설치: $EXT_ID"
    else
        warn "확장 자동설치 실패 — VSCode에서 '$EXT_ID' 직접 설치하세요."
    fi
else
    warn "'code' CLI 없음 → 확장 '$EXT_ID' 수동 설치 필요."
fi

# --- 7. plzrun-vim-indent 확장 빌드(.vsix)+설치 (o/O 블록 들여쓰기) ---
EXT_VIM_SRC="$SCRIPT_DIR/vscode-extension/plzrun-vim-indent"
EXT_VIM_ID="plzrun.plzrun-vim-indent"
if command -v code >/dev/null 2>&1 && command -v zip >/dev/null 2>&1 && [ -d "$EXT_VIM_SRC" ]; then
    VSIX_TMP="$(mktemp -d)"
    mkdir -p "$VSIX_TMP/pkg/extension"
    cp "$EXT_VIM_SRC/package.json" "$EXT_VIM_SRC/extension.js" "$VSIX_TMP/pkg/extension/"
    cat > "$VSIX_TMP/pkg/extension.vsixmanifest" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="plzrun-vim-indent" Version="0.0.3" Publisher="plzrun"/>
    <DisplayName>plzrun vim block indent</DisplayName>
    <Description>Block-aware o/O indentation for VSCodeVim</Description>
    <Categories>Other</Categories>
    <Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.60.0"/></Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets>
</PackageManifest>
XML
    cat > "$VSIX_TMP/pkg/[Content_Types].xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="js" ContentType="application/javascript"/>
  <Default Extension="vsixmanifest" ContentType="text/xml"/>
  <Default Extension="xml" ContentType="text/xml"/>
</Types>
XML
    ( cd "$VSIX_TMP/pkg" && zip -q -r -X "$VSIX_TMP/plzrun-vim-indent.vsix" extension.vsixmanifest "[Content_Types].xml" extension )
    if code --install-extension "$VSIX_TMP/plzrun-vim-indent.vsix" --force >/dev/null 2>&1; then
        log "VSCode 확장 설치: $EXT_VIM_ID (o/O 블록 들여쓰기)"
    else
        warn "plzrun-vim-indent 설치 실패 — o/O 들여쓰기 동작 안 할 수 있음."
    fi
    rm -rf "$VSIX_TMP"
else
    warn "code/zip 없음 또는 확장 소스 없음 → plzrun-vim-indent 설치 건너뜀 (o/O 들여쓰기 미동작)."
fi

echo
log "✅ 설치 완료!"
echo "   • astyle      : $ASTYLE_DEST"
echo "   • 터미널 vim  : 새로 켜고  gg=G"
echo "   • VSCode      : Reload Window 후  gg=G (또는 Format Document)"
echo "   • 제거        : bash uninstall.sh"
