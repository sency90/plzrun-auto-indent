# plzrun-auto-indent — 어떻게 만들었나 (개발 노트)

C/C++ 코드 자동정렬 + vim 손버릇(`ko`) 들여쓰기를 **어느 PC(mac/Linux/WSL)에서도, 네트워크 없이** 재현하는 도구. 이 문서는 "무엇을, 왜, 어떻게" 만들었는지 + 특히 **VSCode 확장/.vsix/JS가 실제로 어떻게 동작하는지**를 처음 보는 사람 기준으로 설명한다.

---

## 0. 큰 그림 — 부품 5개

| 부품 | 정체 | 설치 위치 |
|---|---|---|
| **astyle** | C/C++ 코드 정렬기(포매터) CLI 프로그램 | `~/.local/bin/astyle` (소스에서 직접 빌드) |
| **`~/.astylerc`** | astyle이 따를 "정렬 규칙" 텍스트 파일 | 홈 디렉토리 |
| **`~/.vimrc` 패치** | 터미널 vim의 `gg=G`가 astyle을 부르게 | 홈 |
| **VSCode 설정 + 확장 2개** | VSCode에서도 같은 정렬 + `ko` 들여쓰기 | VSCode user settings / extensions |
| **install.sh / uninstall.sh** | 위 전부를 깔고/지우는 스크립트 | repo |

핵심 철학: **정렬 규칙은 `~/.astylerc` 한 곳**에만 있고, 터미널 vim도 VSCode도 결국 **같은 astyle을 호출**한다 → 어디서 코딩하든 결과가 동일.

---

## 1. astyle — 왜 이걸 쓰고, 왜 직접 빌드하나

### 왜 clang-format이 아니라 astyle?
- clang-format은 **연산자 주변 공백(`=`, `+`, `-`)을 항상 강제 정규화**한다. "공백은 내가 결정"이 불가능.
- astyle은 반대 — **시킨 것만 바꾸고 나머지는 안 건드린다.** `--pad-oper`를 안 주면 연산자 공백을 그대로 둔다. 그래서 채택.

### 왜 소스에서 직접 컴파일하나 (`vendor/astyle-3.6.16/`)
- 회사 PC는 **air-gapped**(외부 네트워크/`apt`/`brew` 불가).
- astyle은 외부 라이브러리 의존이 없는 **순수 C++**. 그래서 **소스를 repo에 동봉**하고, 설치 시 `g++`로 그 자리에서 빌드한다:
  ```
  g++ -O2 -std=c++17 vendor/astyle-3.6.16/src/*.cpp -o ~/.local/bin/astyle
  ```
- astyle 3.6.16은 `std::filesystem`을 써서 **C++17(= g++ 8+ 또는 clang 7+)** 필요. Linux 구버전 g++(8~10)는 `-lstdc++fs`를 추가로 링크해야 해서 install.sh가 "옵션 없이 → 실패하면 `-lstdc++fs` 붙여서" 2단계로 시도한다.
- 개발자 PC엔 `g++`가 항상 있으므로, 이 방식이면 회사/집 어디서나 동일하게 빌드된다.

### `.astylerc` 규칙 요약
`--style=attach`(여는 중괄호 같은 줄), `--break-closing-braces`(else 앞 개행), `--indent=spaces=4`, `--convert-tabs`, `--keep-one-line-blocks/statements`, `--unpad-paren`(`if (`→`if(`), `--indent-namespaces`, `--mode=c`. **연산자 공백은 손 안 댐**(pad 옵션 미사용), **라벨은 0열**(`--indent-labels` 미사용).

---

## 2. 터미널 vim 연동 — `equalprg`

vim에는 "`=`로 들여쓰기 할 때 외부 프로그램에 맡기는" 설정 `equalprg`가 있다. install.sh가 `~/.vimrc`에 추가:
```vim
autocmd FileType c,cpp setlocal equalprg=astyle   " gg=G 하면 버퍼를 astyle에 통과
autocmd FileType make,go setlocal noexpandtab     " Makefile/Go는 탭 유지
```
→ 터미널 vim에서 `gg=G` = 파일 전체를 astyle(`~/.astylerc` 규칙)로 정렬. VSCode와 같은 결과.

---

## 3. VSCode 연동 — settings 병합 (덮어쓰기 절대 금지)

VSCode는 `settings.json`(JSON 파일)로 설정한다. install.sh가 여기에 우리 키들을 **병합**한다. **중요 원칙: 사용자의 다른 설정을 절대 안 건드린다.**

- **JSON 병합은 python으로** 한다(bash로 JSON 안전하게 못 다룸). 기존 파일을 읽어 우리 키만 추가/수정하고 다시 쓴다.
- `[cpp]`/`[c]` 같은 객체도 **통째로 덮어쓰지 않고** 우리 키(`editor.defaultFormatter`)만 끼워 넣는다.
- `editor.autoIndent` 같은 **전역 공통키**는 사용자가 원래 값을 갖고 있었을 수 있으므로, **덮어쓰기 전 원래 값을 백업**(`~/.config/plzrun-auto-indent/orig-settings.json`)했다가 uninstall 때 **정확히 그 값으로 복원**(원래 없었으면 키만 제거)한다.
- 절대 "settings.json 전체를 통째로 백업했다가 통째로 덮어쓰기" 안 한다 — 그러면 설치 후 사용자가 바꾼 다른 설정까지 날아간다.

우리가 넣는 VSCode 설정:
- `customLocalFormatters.formatters` → astyle을 포매터로 등록(아래 확장과 연결)
- `[cpp]`/`[c]` defaultFormatter → astyle
- `editor.autoIndent: "keep"` → **`{`+Enter가 자동으로 3줄로 펼쳐지지 않고 개행 1개만** (vim 손버릇 호환)
- `[makefile]`/`[go]` 탭 강제, `*.mak`/`*.mk` 인식
- `vim.normalModeKeyBindingsNonRecursive` → `o`/`O` 리맵(아래 설명)

경로는 OS별 자동: mac=`~/Library/Application Support/Code/User/...`, Linux=`~/.config/Code/User/...`, Remote-WSL=`~/.vscode-server/...`.

---

## 4. ★ VSCode 확장이란? (.vsix / JS가 실제로 어떻게 동작하나)

여기가 동혁님이 궁금해한 부분. 차근차근.

### 4-1. VSCode 확장은 "실행파일"이 아니다 — 그냥 JavaScript 소스다
- VSCode 자체가 **Electron**(= 크롬 브라우저 엔진 + **Node.js**)으로 만들어졌다. 즉 VSCode 안에는 **JavaScript를 실행하는 엔진(Node.js)** 이 들어있다.
- 그래서 확장은 컴파일된 `.exe` 같은 게 **아니라**, **JavaScript 소스 파일(`extension.js`) 그대로**다. VSCode가 그 JS를 읽어서 자기 Node.js로 실행한다. (파이썬 스크립트를 파이썬이 읽어 실행하는 것과 똑같은 구조.)

### 4-2. 확장 폴더의 구성
우리 확장 `vscode-extension/plzrun-vim-indent/`:
```
package.json   ← 확장 "명세서"(manifest): 이름/버전/진입점/제공하는 명령 목록
extension.js   ← 실제 코드(JavaScript)
```
- `package.json`의 `"main": "./extension.js"` → "내 코드는 여기 있다"고 VSCode에 알려줌.
- `package.json`의 `"contributes": {"commands":[{"command":"plzrun.fixIndent", ...}]}` → "나는 `plzrun.fixIndent`라는 **명령(command)** 을 제공한다"고 등록.
- `"activationEvents": ["onStartupFinished"]` → "VSCode 켜질 때 나를 로드해라."

### 4-3. JS 코드가 하는 일 (extension.js, JS 입문 곁들여)
```js
const vscode = require("vscode");   // VSCode가 주는 'API 도구상자'를 가져옴(import 같은 것)

function activate(context) {         // VSCode가 확장 로드할 때 자동으로 부르는 함수
    context.subscriptions.push(
        vscode.commands.registerCommand("plzrun.fixIndent", fixIndent)
        // "plzrun.fixIndent 명령이 불리면 fixIndent 함수를 실행해라" 라고 등록
    );
}
```
JS 문법 최소 지식:
- `const x = ...` : 변수 선언(상수). `let`은 바뀌는 변수.
- `function 이름(인자){ ... }` : 함수. `(인자) => { ... }`는 같은 걸 짧게 쓴 "화살표 함수".
- `객체.속성` / `객체.메서드()` : 점으로 접근. `vscode.window.activeTextEditor` = "지금 활성 편집기".
- `async` / `await` : 시간이 걸리는 작업(파일 편집 등)을 "기다렸다 다음 줄" 실행하게 해줌.
- `require("vscode")` : VSCode가 확장에게만 주는 특별한 모듈. 이걸로 문서 읽기/커서 이동/줄 편집을 한다.

핵심 함수 `fixIndent`가 하는 일:
1. 지금 커서가 있는 줄 번호를 구한다.
2. **파일 맨 처음부터 그 줄 직전까지 `{` 와 `}` 개수를 세서 "미닫힌 `{` 개수 = 블록 깊이"** 를 계산한다. (문자열/문자리터럴/`//`,`/* */` 주석 안의 괄호는 무시.)
3. 깊이 × 4칸(탭 크기)만큼을 그 줄의 들여쓰기로 **다시 써넣는다**. (`}`로 시작하는 줄은 한 단계 덜.)
4. 커서를 그 들여쓰기 끝으로 옮긴다.

→ 이게 "빈 줄 위가 또 빈 줄이어도 정확히 들여쓰기"되는 이유: **앞 줄을 보고 따라하는 게 아니라, 파일 전체 괄호를 세서 위치로 계산**하니까.

### 4-4. `.vsix`는 뭔가? — 그냥 ZIP 파일이다
- `.vsix`는 특별한 포맷처럼 보이지만 **실체는 zip**이다. 안에:
  ```
  extension.vsixmanifest   ← XML 명세(고정 양식)
  [Content_Types].xml      ← XML(고정 양식)
  extension/               ← 우리 확장 폴더(package.json + extension.js)
  ```
- "설치(`code --install-extension foo.vsix`)" = VSCode가 이 zip을 풀어서 자기 확장 폴더(`~/.vscode/extensions/...`)에 넣고 로드하는 것. **컴파일 같은 건 없다.** JS 소스가 그대로 들어간다.
- 보통은 `vsce`라는 공식 패키징 도구로 .vsix를 만들지만, 우리는 회사 air-gapped 대비해서 **그냥 `zip` 명령으로 직접** .vsix를 만든다(install.sh가 즉석에서 zip → `code --install-extension`). vsce도 네트워크도 필요 없음.

### 4-5. 확장 2개를 쓰는 이유
- **`jkillian.custom-local-formatters`** (남이 만든 확장): VSCode의 "Format Document"가 임의의 CLI를 부를 수 있게 해주는 다리. 이걸로 `gg=G`가 astyle을 호출.
- **`plzrun.plzrun-vim-indent`** (우리가 만든 확장): `o`/`ko`의 블록 들여쓰기. 아래 5장 참고.

---

## 5. "두 요구가 충돌" 문제와 확장으로 푼 방법

동혁님 두 요구:
1. `{}`+Enter = **깔끔히 2줄**(중간 빈 줄 없음)
2. `ko`(open line) = **블록 깊이에 맞는 들여쓰기**(빈 줄에서도)

이 둘은 VSCode의 같은 엔진(`editor.autoIndent`)을 공유해서 **설정값 하나로는 동시에 불가능**:
- `keep` → 1번 OK, 2번 X(0열)
- `full`/`brackets` → 2번 OK, 1번 X(Enter가 펼쳐짐)

그래서 **분리**했다:
- Enter는 `editor.autoIndent: "keep"`로 둬서 1번 해결(깔끔 2줄).
- `o`/`ko`는 **우리 확장 명령으로 따로** 처리해서 2번 해결.
- 연결: VSCodeVim 리맵
  ```json
  {"before":["o"], "after":["o"], "commands":["plzrun.fixIndent"]}
  ```
  = "`o`를 누르면 → vim 기본 `o`(줄 열기 + **입력모드 진입**) → 그다음 우리 `plzrun.fixIndent`(블록 들여쓰기) 실행". (VSCodeVim이 `after`[vim 키]+`commands`[VSCode 명령]를 둘 다 받아준다.)

이래서 `ko` 손버릇 그대로, 입력모드도 되고, 들여쓰기도 블록에 맞는다.

---

## 6. install.sh / uninstall.sh 흐름

**install.sh** (요구사항 검사 → 빌드 성공해야만 실제 설치):
1. 검사: 동봉 소스 존재, `g++`(버전), `python3`(3.6+). 미충족이면 **아무것도 안 바꾸고 중단**.
2. astyle을 임시 폴더에 빌드 → 성공하면 `~/.local/bin/astyle`로 설치.
3. `~/.astylerc` 배치.
4. `~/.vimrc` 패치(마커 블록, 재실행 시 경로 갱신).
5. VSCode settings 병합(위 3장, 백업 포함).
6. 확장 2개 설치(custom-local-formatters + 우리 .vsix 빌드/설치).

**uninstall.sh** (만든 것만 정확히 제거):
- astyle 바이너리(우리가 만든 Artistic Style인지 확인 후), `~/.astylerc`(우리 마커 확인 후), `~/.vimrc` 마커 블록, VSCode settings에서 **우리 키만**(전역키는 백업값으로 복원), 확장 2개. 사용자 다른 설정/리맵은 보존.

---

## 7. 한 줄 요약
규칙은 `~/.astylerc` 하나. 터미널 vim·VSCode 둘 다 결국 astyle 호출. astyle은 소스 동봉해 g++로 빌드(air-gapped). `ko` 들여쓰기 충돌은 **직접 만든 초소형 VSCode 확장(JS, .vsix=zip)** 으로 분리해 해결. 설치/제거는 사용자 설정을 절대 안 깨도록 키 단위로만 건드림.
