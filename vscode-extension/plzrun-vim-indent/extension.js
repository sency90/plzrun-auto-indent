"use strict";
const vscode = require("vscode");

// 파일 시작부터 lineIndex 직전까지의 '미닫힌 중괄호' 개수(블록 깊이)를 센다.
// 문자열/문자리터럴/라인주석/블록주석 안의 { } 는 무시.
function braceDepthBefore(doc, lineIndex) {
    let depth = 0;
    let inBlockComment = false;
    const upto = Math.min(lineIndex, doc.lineCount);
    for (let i = 0; i < upto; i++) {
        const text = doc.lineAt(i).text;
        let inStr = false, inChr = false, j = 0;
        while (j < text.length) {
            const c = text[j], n = text[j + 1];
            if (inBlockComment) {
                if (c === "*" && n === "/") { inBlockComment = false; j += 2; continue; }
                j++; continue;
            }
            if (inStr) {
                if (c === "\\") { j += 2; continue; }
                if (c === '"') inStr = false;
                j++; continue;
            }
            if (inChr) {
                if (c === "\\") { j += 2; continue; }
                if (c === "'") inChr = false;
                j++; continue;
            }
            if (c === "/" && n === "/") break;            // 라인 주석
            if (c === "/" && n === "*") { inBlockComment = true; j += 2; continue; }
            if (c === '"') { inStr = true; j++; continue; }
            if (c === "'") { inChr = true; j++; continue; }
            if (c === "{") depth++;
            else if (c === "}") depth = Math.max(0, depth - 1);
            j++;
        }
    }
    return depth;
}

// 현재 커서 줄의 들여쓰기를 '블록 깊이'에 맞게 다시 설정 (빈 줄 포함).
async function fixIndent() {
    const ed = vscode.window.activeTextEditor;
    if (!ed) return;
    const doc = ed.document;
    const line = ed.selection.active.line;

    let d = braceDepthBefore(doc, line);
    const curText = doc.lineAt(line).text;
    if (/^\s*\}/.test(curText)) d = Math.max(0, d - 1); // '}' 로 시작하면 여는 짝과 같은 깊이

    const opt = ed.options;
    const tabSize = typeof opt.tabSize === "number" ? opt.tabSize : 4;
    const useSpaces = opt.insertSpaces !== false;
    const indent = useSpaces ? " ".repeat(d * tabSize) : "\t".repeat(d);

    const lead = (curText.match(/^[ \t]*/) || [""])[0].length;
    await ed.edit(
        (eb) => eb.replace(new vscode.Range(line, 0, line, lead), indent),
        { undoStopBefore: false, undoStopAfter: false }
    );
    const pos = new vscode.Position(line, indent.length);
    ed.selection = new vscode.Selection(pos, pos);
}

// 선택 영역의 각 줄을, 파일 전체 브래킷 깊이에 맞게 재들여쓰기 (vim '=' 처럼).
// 선택 밖은 절대 안 건드리되, 깊이는 '파일 처음부터'의 미닫힌 { 개수로 계산하므로
// 바깥 블록 맥락(들여쓰기)이 그대로 반영된다. (들여쓰기만 손대고 토큰 간격은 안 건드림)
async function reindentSelection() {
    const ed = vscode.window.activeTextEditor;
    if (!ed) return;
    const doc = ed.document;

    const lineSet = new Set();
    for (const sel of ed.selections) {
        let a = sel.start.line, b = sel.end.line;
        // 줄 단위 선택(V)에서 끝이 다음 줄 0열이면 그 줄은 제외
        if (b > a && sel.end.character === 0) b -= 1;
        for (let l = a; l <= b; l++) lineSet.add(l);
    }
    const lines = [...lineSet].sort((x, y) => x - y);
    if (lines.length === 0) return;

    const opt = ed.options;
    const tabSize = typeof opt.tabSize === "number" ? opt.tabSize : 4;
    const useSpaces = opt.insertSpaces !== false;

    await ed.edit((eb) => {
        for (const line of lines) {
            const txt = doc.lineAt(line).text;
            if (txt.trim() === "") {                 // 빈 줄은 비운 채로(공백만 제거)
                const lead0 = (txt.match(/^[ \t]*/) || [""])[0].length;
                if (lead0 > 0) eb.replace(new vscode.Range(line, 0, line, lead0), "");
                continue;
            }
            let d = braceDepthBefore(doc, line);
            if (/^\s*[}\])]/.test(txt)) d = Math.max(0, d - 1);
            const indent = useSpaces ? " ".repeat(d * tabSize) : "\t".repeat(d);
            const lead = (txt.match(/^[ \t]*/) || [""])[0].length;
            eb.replace(new vscode.Range(line, 0, line, lead), indent);
        }
    }, { undoStopBefore: true, undoStopAfter: true });
}

function activate(context) {
    context.subscriptions.push(
        vscode.commands.registerCommand("plzrun.fixIndent", fixIndent),
        vscode.commands.registerCommand("plzrun.reindentSelection", reindentSelection)
    );
}
function deactivate() {}

module.exports = { activate, deactivate };
