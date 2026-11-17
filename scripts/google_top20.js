// 在谷歌的搜索结果页里运行：把一个词的第一页、第二页重新取一次原文，读出自然结果。
// 用在浏览器把页面自动翻成了中文、翻译又关不掉的时候。取回的标题是英文原文。
//
// 用法（在已经打开的 google.com/search 页面里，用浏览器工具的「运行页面脚本」）：
//   1. 先运行这一整段，定义 googleTop20。
//   2. const text = await googleTop20('snow day calculator', 1);   只取第一页
//      看完第一页，要翻第二页的：
//      const text = await googleTop20('snow day calculator', 2);   只补取第二页，返回两页合起来的
//      后面那个数不写，是两页一起取：await googleTop20('snow day calculator')
//   3. 把 text 存成文件。有的浏览器工具一次只带得回约 1000 个字：
//      把 text 存在 window 上，再用 text.split('\n').slice(0, 8).join('\n') 这样一段一段取。
//
// 输出每行：名次 | p1 或 p2 | 域名 | 路径 | 标题
// 只回域名和路径，不带问号后面的部分：有的浏览器工具会把带查询串的网址整段挡掉。
// 两页之间停两三秒。碰到人机验证就停，不做验证。
async function googleTop20(query, pages) {
  // 取过的第一页记在页面里，补取第二页时名次接着往下排、重复的网址不再记
  const store = (window.__googleTop20 = window.__googleTop20 || {});
  let st = store[query];
  let todo;
  if (pages === 2 && st && st.done.includes('p1') && !st.done.includes('p2')) {
    todo = [['p2', 10]];
  } else {
    st = store[query] = { lines: ['## ' + query], seen: new Set(), rank: 0, done: [] };
    todo = pages === 1 ? [['p1', 0]] : [['p1', 0], ['p2', 10]];
  }
  for (const [page, start] of todo) {
    const url = '/search?q=' + encodeURIComponent(query).replace(/%20/g, '+') + '&gl=us&hl=en' + (start ? '&start=' + start : '');
    const res = await fetch(url, { credentials: 'include' });
    if (res.url.includes('/sorry') || res.status !== 200) {
      st.lines.push('!! ' + page + ' 没取到：状态 ' + res.status + (res.url.includes('/sorry') ? '，出现人机验证' : ''));
      break;
    }
    const html = await res.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    let got = 0;
    doc.querySelectorAll('#search a h3, #rso a h3, #botstuff a h3').forEach((h3) => {
      const a = h3.closest('a');
      if (!a) return;
      let u;
      try { u = new URL(a.getAttribute('href') || '', 'https://www.google.com'); } catch (e) { return; }
      if (u.hostname.endsWith('google.com') && u.pathname === '/url') {
        try { u = new URL(u.searchParams.get('q')); } catch (e) { return; }
      }
      if (u.hostname.endsWith('google.com') && u.pathname === '/search') return;
      // 「大家还问」、视频和图片的横排、广告，不算自然结果
      if (h3.closest('[data-initq], .related-question-pair, g-scrolling-carousel, [data-text-ad], #tads, #tadsb')) return;
      const key = u.hostname + u.pathname;
      if (st.seen.has(key)) return;
      st.seen.add(key);
      st.rank += 1;
      got += 1;
      st.lines.push([st.rank, page, u.hostname.replace(/^www\./, ''), u.pathname, h3.textContent.trim().replace(/\s+/g, ' ')].join(' | '));
    });
    if (!got) st.lines.push('!! ' + page + ' 一条自然结果都没读出来，网页长度 ' + html.length);
    st.done.push(page);
    await new Promise((r) => setTimeout(r, 2000 + Math.random() * 1500));
  }
  return st.lines.join('\n');
}
