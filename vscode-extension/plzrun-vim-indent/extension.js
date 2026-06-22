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

function activate(context) {
    context.subscriptions.push(
        vscode.commands.registerCommand("plzrun.fixIndent", fixIndent)
    );
}
function deactivate() {}

module.exports = { activate, deactivate };
