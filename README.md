# plzrun-auto-indent

C/C++ 코드 자동정렬 환경을 **어느 PC(macOS / Linux / WSL Ubuntu)에서도, 외부 네트워크 없이** 한 번에 세팅하는 설치기.

> astyle 을 패키지매니저(apt/brew)·네트워크 없이 **repo 동봉 소스에서 g++ 로 직접 빌드**하므로 회사 air-gapped 환경에서도 동작합니다.

## 설치 / 제거

```bash
cd ~/github/plzrun-auto-indent
bash install.sh      # 설치
bash uninstall.sh    # 완전 제거 (만든 것만 정확히 되돌림)
```

설치 후:
- **터미널 vim**: 새로 켜고 `gg=G` → astyle 규칙으로 정렬
- **VSCode**: `Reload Window` 후 `gg=G`(VSCodeVim) 또는 Format Document

## 요구사항 (install.sh 가 먼저 검사, 미충족 시 아무것도 안 건드리고 중단)

| 도구 | 최소 | 비고 |
|---|---|---|
| `g++` | **8+** (또는 clang 7+) | astyle 3.6.16 = C++17/`std::filesystem`. 빌드 실패 시 설치 중단 |
| `python3` | **3.6+** | VSCode settings.json 병합용 |
| `code` (선택) | — | 있으면 VSCode 확장 자동 설치 |

검사 흐름: **요구사항 검사 → astyle 임시 빌드 성공 → 그 다음에야 실제 설치**. 어느 한 단계라도 실패하면 시스템을 전혀 변경하지 않고 멈춥니다.

## install.sh 가 하는 일

1. **astyle 빌드** — `vendor/astyle-3.6.16/src/*.cpp` 를 `g++ -std=c++17` 로 컴파일 → `~/.local/bin/astyle` (Linux 구버전은 `-lstdc++fs` 자동 폴백)
2. **`~/.astylerc`** 배치 — 정렬 규칙 단일 소스 (`astylerc` 복사)
3. **`~/.vimrc`** 패치 — `equalprg=<astyle 절대경로>`(c/cpp) + Makefile/Go `noexpandtab` (마커 블록, 재실행 시 경로 갱신)
4. **VSCode 전역 settings.json 병합** (기존 설정 보존) — astyle 포매터 등록 + cpp/c 기본 포매터 + `editor.autoIndent: "keep"`(**전역/모든 언어**: `{` 사이 Enter 시 자동 펼침 없이 개행 1개, vim 손버릇 호환) + Makefile/Go 탭 + `*.mak`/`*.mk`/`GNUmakefile` 인식. macOS / Linux / Remote-WSL 경로 자동 판별.
   - `[cpp]`/`[c]` 는 덮어쓰지 않고 우리 키만 병합. `editor.autoIndent` 같은 **전역 공통키는 원래값을 `~/.config/plzrun-auto-indent/orig-settings.json` 에 백업** → uninstall 시 원래값으로 **완벽 복원**(원래 없었으면 제거)
   - **VSCodeVim `o`/`O` 리맵** 추가(`vim.normalModeKeyBindingsNonRecursive`): native `o`(줄 열기+입력모드) 후 `reindent`로 문맥 맞춤 들여쓰기. `autoIndent:keep`라 `{` 사이 Enter는 1줄이면서도 `ko` 손버릇에서 커서가 올바른 들여쓰기 위치로 감. 배열엔 **우리 2개 항목만 append**(사용자 다른 리맵 보존), uninstall 시 **우리 항목만 제거**
5. **VSCode 확장 자동 설치** — `jkillian.custom-local-formatters` (`code` 있을 때)

## uninstall.sh 가 되돌리는 것

- `~/.local/bin/astyle` (우리가 빌드한 Artistic Style 인지 확인 후)
- `~/.astylerc` (우리 마커 헤더 있을 때만)
- `~/.vimrc` 의 `plzrun-auto-indent` 마커 블록
- VSCode settings.json 에서 **우리가 넣은 키만** (사용자 다른 설정 보존)
- VSCode 확장 `jkillian.custom-local-formatters`

## 정렬 규칙 (astylerc)

| 항목 | 동작 |
|---|---|
| 여는 중괄호 | 같은 줄 + 공백 한 칸 (`if(x) {`) |
| else/catch | 앞에서 개행 |
| 들여쓰기 | 스페이스 4칸 (탭→스페이스 변환) |
| `if (`/`for (`/`while (` | → `if(` 강제 |
| namespace 내부 | 들여쓰기 |
| goto 라벨 | 0열(맨 왼쪽), `BRK:;` 한 줄 유지 |
| 한 줄 함수/블록 | 보존 |
| 연산자(`=` `+` `-`) 공백 | **건드리지 않음** (사용자 자유) |

규칙 변경: `astylerc` 수정 후 `install.sh` 재실행.

## 동작 원리

정렬은 전부 `astyle` + `~/.astylerc` 가 수행. VSCode·터미널 vim 의 `gg=G` 는 같은 astyle 을 호출하는 "방아쇠"라 **두 환경 결과가 동일**.

## 구성

```
plzrun-auto-indent/
├── install.sh
├── uninstall.sh
├── astylerc
├── README.md
├── LICENSE
└── vendor/astyle-3.6.16/   # astyle 소스 (MIT), g++로 빌드됨
```

## 라이선스

이 프로젝트는 **MIT License** (루트 `LICENSE`).

번들된 third-party:
- **Artistic Style (astyle)** — MIT License, (c) The Artistic Style Authors.
  소스: `vendor/astyle-3.6.16/`, 라이선스 전문: `vendor/astyle-3.6.16/LICENSE.md`,
  홈: https://astyle.sourceforge.net/
