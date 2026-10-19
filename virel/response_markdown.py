"""Optional DOM-to-Markdown serializer; the original plain reader stays in dom.py."""

RENDER_MARKDOWN = r"""(root) => {
    const ignored = 'button, mat-icon, .material-symbols-outlined, .mat-expansion-panel-header, .code-block-header, ms-citation-chunk, .citation, ms-thought-chunk, .thought-activity-host, ms-function-call-chunk, ms-function-response-chunk, script, style, template';
    // Underscores inside identifiers are literal Markdown, not emphasis markers.
    const escape = text => text.replace(/([\\\x60*[\]<>~])/g, '\\$1')
        .replace(/(?<![\p{L}\p{N}_])_|_(?![\p{L}\p{N}_])/gu, '\\_');
    const join = nodes => Array.from(nodes, render).reduce((out, part) =>
        out.endsWith('\n') && part.startsWith('\n')
            ? out.replace(/\n+$/, '') + '\n\n' + part.replace(/^\n+/, '') : out + part, '');
    const block = text => '\n\n' + text.trim() + '\n\n';
    const fence = text => '\x60'.repeat(Math.max(3,
        ...Array.from(text.matchAll(/\x60+/g), match => match[0].length + 1)));
    function codeBlock(node) {
        const pre = node.matches('pre') ? node : node.querySelector('pre');
        const code = pre?.querySelector('code');
        const text = pre ? (code || pre).textContent : join(node.childNodes).trim();
        const label = (node.querySelector('.title-text')?.textContent || '').trim();
        const language = (code?.className || '').match(/(?:^|\s)language-([a-zA-Z0-9_+-]+)/)?.[1] || (/^[a-zA-Z0-9_+-]{1,32}$/.test(label) && label.toLowerCase() !== 'text' ? label.toLowerCase() : '');
        const ticks = fence(text);
        return block(ticks + language + '\n' + text + (text.endsWith('\n') ? '' : '\n') + ticks);
    }
    function list(node) {
        let number = Number(node.getAttribute('start') || 1);
        const lines = Array.from(node.querySelectorAll('li')).filter(item =>
            item.parentElement.closest('ul, ol') === node && !item.closest(ignored + ', [hidden], [aria-hidden="true"]') && item.getClientRects().length).map(item => {
            const marker = node.tagName === 'OL' ? String(number++) + '. ' : '- ';
            const parts = Array.from(item.childNodes).map(child =>
                child.nodeType === 1 && /^(UL|OL)$/.test(child.tagName)
                    ? '\n' + list(child).trim() : render(child));
            const body = parts.join('').trim();
            return marker + body.split('\n').join('\n' + ' '.repeat(marker.length));
        });
        return block(lines.join('\n'));
    }
    function table(node) {
        const rows = Array.from(node.querySelectorAll('tr')).filter(row => row.closest('table') === node)
            .map(row => Array.from(row.children).filter(cell => /^(TH|TD)$/.test(cell.tagName))
                .map(cell => join(cell.childNodes).trim().replace(/\|/g, '\\|').replace(/ *\n+ */g, '<br>')));
        if (!rows.length) return '';
        const width = Math.max(...rows.map(row => row.length));
        const hasHeader = node.querySelector('tr')?.querySelector('th') !== null;
        const header = hasHeader ? rows.shift() : [];
        const line = row => '| ' + Array.from({length: width}, (_, i) => row[i] || '').join(' | ') + ' |';
        return block([line(header), line(Array(width).fill('---')), ...rows.map(line)].join('\n'));
    }
    function render(node) {
        if (node.nodeType === 3) return escape(node.textContent.replace(/\s+/g, ' '));
        if (node.nodeType !== 1 || node.matches(ignored) || node.hidden ||
            node.getAttribute('aria-hidden') === 'true') return '';
        const style = getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden') return '';
        const tag = node.tagName;
        if (tag === 'PRE' || tag === 'MS-CODE-BLOCK' || tag === 'MS-CODE-CHUNK') return codeBlock(node);
        if (tag === 'UL' || tag === 'OL') return list(node);
        if (tag === 'TABLE') return table(node);
        if (tag === 'BR') return '  \n';
        if (tag === 'HR') return block('---');
        if (tag === 'CODE' || node.classList.contains('inline-code')) {
            const text = node.textContent;
            const ticks = '\x60'.repeat(Math.max(1,
                ...Array.from(text.matchAll(/\x60+/g), match => match[0].length + 1)));
            const pad = /^\x60|\x60$|^ .* $/.test(text) ? ' ' : '';
            return ticks + pad + text + pad + ticks;
        }
        const text = join(node.childNodes);
        if (/^H[1-6]$/.test(tag)) return block('#'.repeat(Number(tag[1])) + ' ' + text.trim());
        if (tag === 'STRONG' || tag === 'B') return '**' + text + '**';
        if (tag === 'EM' || tag === 'I') return '*' + text + '*';
        if (tag === 'DEL' || tag === 'S' || tag === 'STRIKE') return '~~' + text + '~~';
        if (tag === 'A') {
            const url = node.getAttribute('href') || '';
            if (!/^(https?:|mailto:|\/|#)/i.test(url) || /[\x00-\x1f\x7f]/.test(url)) return text;
            const safe = url.replace(/[<>\s]/g, char => encodeURIComponent(char));
            return '[' + text + '](<' + safe + '>)';
        }
        if (tag === 'BLOCKQUOTE') return block(text.trim().split('\n').map(line => '> ' + line).join('\n'));
        if (tag === 'P' || tag === 'DIV') return block(text);
        return text;
    }
    // shortcut: reconstruct common rendered Markdown, not exact source/CSS/math/citation markup.
    return render(root).trim();
}"""
