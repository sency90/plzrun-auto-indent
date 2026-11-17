#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""설정 파일을 다른 기기로 옮겨도 gg=G 가 도는지 시험 (임시 HOME, headless).

    python3 tests/test_portable_paths.py

배경
  리눅스에서 install.sh 가 VSCode settings.json 에 "/home/<이름>/.local/bin/astyle" 을
  써넣었고, 그 설정이 맥으로 넘어와 gg=G 가 "exited with code 127" 로 실패했다.
  설치기가 쓰는 값은 실행 시점에 그 기기의 홈으로 풀려야 한다.

하는 일
  1) 임시 HOME(A)에 "옛 판이 남긴 절대 경로 값"을 미리 넣어 두고 install.sh 를 돌린다.
     → 옛 값이 새 값으로 바뀌는지, 설정 파일에 홈 절대 경로가 하나도 없는지 본다.
  2) A 를 통째로 다른 경로(B, 이름에 공백 포함)로 옮긴다. A 는 사라진다.
     → VSCode 포매터 확장이 하는 대로(셸로 명령 실행, 표준 입력으로 코드) 돌려 정렬되는지,
       터미널 vim 의 gg=G, V= 가 되는지, 도우미가 없을 때의 equalprg 길도 되는지 본다.
  3) B 에서 uninstall.sh 를 돌려 새 값과 옛 값 모두 지워지는지 본다.
사용자의 실제 설정 파일은 건드리지 않는다. python 3.6 에서도 돈다.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []
COUNT = [0]

OLD_ASTYLE = "/home/plzrun/.local/bin/astyle"       # 옛 판이 리눅스에서 써넣던 값
NEW_CMD = '"$HOME/.local/bin/astyle"'

SRC = "int main(){\nif(1){\nint a=1;\n}\nreturn 0;\n}\n"


def check(name, ok, detail=""):
    COUNT[0] += 1
    if not ok:
        FAILS.append(name)
        print("FAIL %s %s" % (name, detail))


def settings_rel():
    if platform.system() == "Darwin":
        return "Library/Application Support/Code/User/settings.json"
    return ".config/Code/User/settings.json"


def run(args, env, **kw):
    return subprocess.run(args, env=env, stdin=kw.pop("stdin", subprocess.DEVNULL),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)


def old_vimrc_block():
    return ('\n" >>> plzrun-auto-indent >>>\n'
            "let g:plzrun_astyle = '%s'\n"
            "let g:plzrun_python = '/usr/bin/python3'\n"
            "if filereadable('/home/plzrun/.local/share/plzrun-auto-indent/plzrun-reindent.vim')\n"
            "  execute 'source' fnameescape('/home/plzrun/.local/share/plzrun-auto-indent/plzrun-reindent.vim')\n"
            "else\n"
            "  autocmd FileType c,cpp setlocal equalprg=%s\n"
            "endif\n"
            '" <<< plzrun-auto-indent <<<\n' % (OLD_ASTYLE, OLD_ASTYLE))


def vim_run(tmp, env, vimrc, text, cmds, name):
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write(text)
    rc = os.path.join(tmp, name + ".rc.vim")
    with open(rc, "w") as f:
        f.write("execute 'source' fnameescape('%s')\nfiletype plugin indent on\n" % vimrc)
    args = ["vim", "-Es", "-N", "-i", "NONE", "-u", rc]
    for c in cmds:
        args += ["-c", c]
    args += ["-c", "wq", path]
    subprocess.run(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=60)
    with open(path) as f:
        return f.read()


def main():
    tmp = tempfile.mkdtemp(prefix="plzrun-porttest-")
    try:
        home_a = os.path.join(tmp, "homeA")
        os.makedirs(home_a)
        shim = os.path.join(tmp, "shim")
        os.makedirs(shim)
        with open(os.path.join(shim, "code"), "w") as f:      # VSCode CLI 막기
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(os.path.join(shim, "code"), 0o755)
        path_env = shim + os.pathsep + os.environ["PATH"]

        # --- 옛 판이 남긴 상태를 미리 만든다 ---
        sp_a = os.path.join(home_a, settings_rel())
        os.makedirs(os.path.dirname(sp_a))
        with open(sp_a, "w") as f:
            json.dump({"editor.fontSize": 13,
                       "customLocalFormatters.formatters":
                           [{"command": OLD_ASTYLE, "languages": ["cpp", "c"]}]}, f)
        with open(os.path.join(home_a, ".vimrc"), "w") as f:
            f.write('" 사용자 줄\nset nocompatible\n' + old_vimrc_block())

        env_a = dict(os.environ, HOME=home_a, PATH=path_env)
        r = run(["bash", os.path.join(REPO, "install.sh")], env_a)
        if r.returncode != 0:
            sys.stdout.write(r.stdout.decode("utf-8", "replace"))
            raise SystemExit("install.sh 실패")

        # --- 1) 설정 파일에 기기 종속 경로가 없는가 ---
        raw = open(sp_a).read()
        cfg = json.loads(raw)
        fm = cfg.get("customLocalFormatters.formatters")
        check("settings-command-is-home-var",
              fm == [{"command": NEW_CMD, "languages": ["cpp", "c"]}], repr(fm))
        check("settings-old-abs-replaced", OLD_ASTYLE not in raw)
        check("settings-no-install-home", home_a not in raw and os.path.realpath(home_a) not in raw)
        check("settings-keeps-user-keys", cfg.get("editor.fontSize") == 13)
        if platform.system() == "Darwin":
            kb = os.path.join(os.path.dirname(sp_a), "keybindings.json")
            check("keybindings-no-install-home", home_a not in open(kb).read())

        vimrc_a = open(os.path.join(home_a, ".vimrc")).read()
        check("vimrc-one-block", vimrc_a.count(">>> plzrun-auto-indent >>>") == 1)
        check("vimrc-old-abs-replaced", "/home/plzrun" not in vimrc_a, vimrc_a)
        check("vimrc-no-install-home", home_a not in vimrc_a, vimrc_a)
        check("vimrc-astyle-home-var",
              "let g:plzrun_astyle = $HOME . '/.local/bin/astyle'" in vimrc_a, vimrc_a)
        check("vimrc-keeps-user-lines", vimrc_a.startswith('" 사용자 줄\nset nocompatible\n'))

        # 기준 결과: 설치된 astyle 을 직접 실행
        want = subprocess.run([os.path.join(home_a, ".local/bin/astyle")], input=SRC.encode(),
                              stdout=subprocess.PIPE, env=env_a, check=True).stdout.decode()
        check("astyle-changes-sample", want != SRC and "    int a=1;" in want, want)

        # --- 2) 홈을 통째로 다른 경로로 옮긴다(이름에 공백) ---
        home_b = os.path.join(tmp, "moved home B")
        shutil.move(home_a, home_b)
        check("old-home-gone", not os.path.exists(home_a))
        env_b = dict(os.environ, HOME=home_b)
        sp_b = os.path.join(home_b, settings_rel())
        cmd = json.load(open(sp_b))["customLocalFormatters.formatters"][0]["command"]

        # 포매터 확장(jkillian.custom-local-formatters)은 spawn(command, {cwd, shell:true}) 로
        # 실행하고 표준 입력으로 코드를 준다. 유닉스에서 shell:true 는 /bin/sh -c 이다.
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        r = subprocess.run(["/bin/sh", "-c", cmd], input=SRC.encode(), cwd=work, env=env_b,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        check("moved-vscode-command-runs", r.returncode == 0,
              "code=%s %s" % (r.returncode, r.stderr.decode("utf-8", "replace")))
        check("moved-vscode-command-output", r.stdout.decode() == want)
        if shutil.which("node"):                               # 있으면 확장과 똑같은 호출로 한 번 더
            js = ("const p=require('child_process').spawn(process.argv[1],{cwd:process.argv[2],shell:true});"
                  "let o='';p.stdout.on('data',c=>o+=c);"
                  "p.on('close',c=>{process.stdout.write(o);process.exit(c)});"
                  "p.stdin.write(process.argv[3]);p.stdin.end();")
            r = subprocess.run(["node", "-e", js, cmd, work, SRC], env=env_b,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            check("moved-node-spawn-shell", r.returncode == 0 and r.stdout.decode() == want,
                  "code=%s" % r.returncode)
        # 옛 값은 옮긴 기기에서 실제로 127 로 실패한다(이번 버그의 재현)
        r = subprocess.run(["/bin/sh", "-c", OLD_ASTYLE], input=SRC.encode(), env=env_b,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        check("old-abs-fails-127", r.returncode == 127, "code=%s" % r.returncode)

        # 터미널 vim: 옮긴 홈의 ~/.vimrc 그대로
        vimrc_b = os.path.join(home_b, ".vimrc")
        if shutil.which("vim"):
            got = vim_run(tmp, env_b, vimrc_b, SRC, ["normal gg=G"], "full.cpp")
            check("moved-vim-gg=G", got == want, repr(got))
            got = vim_run(tmp, env_b, vimrc_b, want.replace("    int a=1;", "int a=1;"),
                          ["normal 3GV="], "range.cpp")
            check("moved-vim-range", got == want, repr(got))
            # python3 경로가 그 기기에 없어도(다른 기기에서 넘어온 값) PATH 의 python3 로 돈다
            rc2 = os.path.join(tmp, "nopy.vimrc")
            lines = open(vimrc_b).read().split("\n")
            lines = [("let g:plzrun_python = '/no/such/dir/python3'"
                      if l.startswith("let g:plzrun_python") else l) for l in lines]
            with open(rc2, "w") as f:
                f.write("\n".join(lines))
            got = vim_run(tmp, env_b, rc2, SRC, ["normal gg=G"], "nopy.cpp")
            check("moved-vim-python-fallback", got == want, repr(got))
            # 도우미가 없을 때의 equalprg 길(공백 든 홈 경로 포함)
            helper = os.path.join(home_b, ".local/share/plzrun-auto-indent/plzrun-reindent.vim")
            os.rename(helper, helper + ".off")
            got = vim_run(tmp, env_b, vimrc_b, SRC, ["normal gg=G"], "fallback.cpp")
            os.rename(helper + ".off", helper)
            check("moved-vim-equalprg-fallback", got == want, repr(got))
        else:
            print("(vim 없음: vim 시험 건너뜀)")

        # --- 3) 옮긴 홈에서 제거: 새 값도 우리 것으로 알아보고 지운다 ---
        r = run(["bash", os.path.join(REPO, "uninstall.sh")], dict(env_b, PATH=path_env))
        after = json.load(open(sp_b))
        check("uninstall-removes-new-value", "customLocalFormatters.formatters" not in after, repr(after))
        check("uninstall-removes-formatter", "[cpp]" not in after and "[c]" not in after, repr(after))
        check("uninstall-keeps-user-keys", after.get("editor.fontSize") == 13)
        body = open(vimrc_b).read()
        check("uninstall-vimrc", "plzrun" not in body and body.startswith('" 사용자 줄\n'), body)
        check("uninstall-astyle", not os.path.exists(os.path.join(home_b, ".local/bin/astyle")))

        # 옛 절대 경로 값만 남은 설정도 지운다
        with open(sp_b, "w") as f:
            json.dump({"editor.fontSize": 13,
                       "customLocalFormatters.formatters":
                           [{"command": OLD_ASTYLE, "languages": ["cpp", "c"]}]}, f)
        run(["bash", os.path.join(REPO, "uninstall.sh")], dict(env_b, PATH=path_env))
        after = json.load(open(sp_b))
        check("uninstall-removes-old-value", after == {"editor.fontSize": 13}, repr(after))

        # --- 설치기 본문에 절대 경로를 설정에 넣는 코드가 되살아나지 않았는가 ---
        inst = open(os.path.join(REPO, "install.sh")).read()
        check("install-no-abs-into-settings", 'os.environ["ASTYLE_DEST"]' not in inst)
        check("install-no-abs-equalprg", "equalprg=$ASTYLE_DEST" not in inst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("%d checks, %d failed" % (COUNT[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
