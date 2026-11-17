" plzrun-auto-indent: C/C++ 범위 '=' 를 파일 전체 맥락으로 정렬
"
" equalprg 만 쓰면 '=' 가 선택한 줄만 astyle 에 넘겨서, 선택 줄이 바깥 블록
" 깊이를 잃고 0열에 붙는다. 여기서는 '=' 연산자(V=, ==, =ip, =i{, gg=G …)를
" 가로채 버퍼 전체를 plzrun_reindent.py 에 넘기고, 돌려받은 줄로 범위만 바꾼다.
" gg=G 는 지금처럼 astyle 결과를 그대로 쓴다.
"
" install.sh 가 ~/.vimrc 마커 블록에서 아래 두 값을 정한 뒤 이 파일을 읽는다.
"   g:plzrun_astyle   astyle 경로 (vimrc 에는 $HOME . '/.local/bin/astyle' 로 적힌다)
"   g:plzrun_python   python3 경로
" vim 7.4 에서도 돌게 쓴다(회사 Linux/WSL).

if exists('g:loaded_plzrun_reindent')
  finish
endif
let g:loaded_plzrun_reindent = 1

let s:helper = expand('<sfile>:p:h') . '/plzrun_reindent.py'

function! s:IsTarget() abort
  return &filetype ==# 'c' || &filetype ==# 'cpp'
endfunction

" 'g@' 로 바꿔 줄 = 연산자. c/cpp 가 아니면 원래 '=' 그대로.
function! PlzrunReindentExpr() abort
  if !s:IsTarget()
    return '='
  endif
  set operatorfunc=PlzrunReindentOp
  return 'g@'
endfunction

function! PlzrunReindentOp(type) abort
  call PlzrunReindentLines(line("'["), line("']"))
endfunction

function! PlzrunReindentLines(first, last) abort
  let l:first = min([a:first, a:last])
  let l:last = max([a:first, a:last])
  let l:astyle = get(g:, 'plzrun_astyle', 'astyle')
  let l:python = get(g:, 'plzrun_python', 'python3')
  if !executable(l:python)
    let l:python = 'python3'
  endif
  let l:cmd = shellescape(l:python) . ' ' . shellescape(s:helper) . ' '
        \ . l:first . ' ' . l:last . ' ' . shellescape(l:astyle)
  " 리스트로 넘기면 마지막 줄 뒤 줄바꿈이 빠져 끝의 빈 줄이 사라진다 → 문자열로
  let l:input = join(getline(1, '$'), "\n") . "\n"
  if exists('*systemlist')
    let l:new = systemlist(l:cmd, l:input)
  else
    let l:new = split(system(l:cmd, l:input), "\n", 1)
    if !empty(l:new) && l:new[-1] ==# ''
      call remove(l:new, -1)
    endif
  endif
  if v:shell_error || empty(l:new)
    echohl ErrorMsg
    echomsg 'plzrun-auto-indent: 정렬 실패 (' . v:shell_error . ') '
          \ . join(l:new, ' ')
    echohl None
    return
  endif
  let l:old = getline(l:first, l:last)
  if l:new ==# l:old
    call cursor(l:first, 1)
    normal! ^
    return
  endif
  let l:n = len(l:old)
  let l:m = len(l:new)
  " 바뀐 줄만 고친다(같은 줄은 그대로 둬 표시·마크가 흔들리지 않게)
  let l:i = 0
  while l:i < min([l:n, l:m])
    if l:old[l:i] !=# l:new[l:i]
      call setline(l:first + l:i, l:new[l:i])
    endif
    let l:i += 1
  endwhile
  if l:m > l:n
    call append(l:first + l:n - 1, l:new[l:n :])
  elseif l:m < l:n
    silent execute (l:first + l:m) . ',' . l:last . 'delete _'
  endif
  call cursor(l:first, 1)
  normal! ^
  if l:m != l:n
    echo 'plzrun-auto-indent: ' . l:n . '줄 -> ' . l:m . '줄'
  endif
endfunction

function! s:Setup() abort
  if !s:IsTarget()
    return
  endif
  " 매핑이 안 먹는 경로(:normal! = 등)는 지금처럼 astyle 로 간다
  " equalprg 는 셸로 실행된다 → 홈 경로에 공백이 있어도 한 단어가 되게 shellescape
  execute 'setlocal equalprg=' . escape(shellescape(get(g:, 'plzrun_astyle', 'astyle')), ' \|"')
  nnoremap <buffer> <silent> <expr> = PlzrunReindentExpr()
  xnoremap <buffer> <silent> <expr> = PlzrunReindentExpr()
  nnoremap <buffer> <silent> <expr> == PlzrunReindentExpr() ==# 'g@' ? 'g@_' : '=='
endfunction

augroup plzrun_reindent
  autocmd!
  autocmd FileType c,cpp call s:Setup()
augroup END
