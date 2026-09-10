(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const SEL_LIST = `[data-e2e="comment-list"]`;
  const SEL_ITEM = `[data-e2e="comment-item"]`;
  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const getCount = () => { const l = q(SEL_LIST); return l ? l.querySelectorAll(SEL_ITEM).length : -1; };
  const url = location.href;

  // 1) 等待评论列表出现且有条目
  let L = null, waited = 0;
  for (let i = 0; i < 40; i++) {
    L = q(SEL_LIST);
    if (L && L.querySelectorAll(SEL_ITEM).length > 0) break;
    await sleep(1000); waited++;
  }
  if (!L) return { ok: false, reason: "no_list", url: url, n: 0, comments: [], waited: waited };
  if (getCount() === 0) {
    const txt = (L.innerText || "").slice(0, 80);
    return { ok: true, url: url, n: 0, comments: [], txt: txt, waited: waited };
  }

  await sleep(3000); // 让容器高度与滚动容器就绪

  // 2) 健壮的滚动容器探测：向上找第一个可滚动祖先
  const findScroller = () => {
    const list = q(SEL_LIST);
    if (!list) return null;
    let el = list;
    while (el && el !== document.documentElement && el !== document.body) {
      const st = getComputedStyle(el);
      const scrollable = /auto|scroll/.test(st.overflowY) || /auto|scroll/.test(st.overflowX);
      if (scrollable && el.scrollHeight > el.clientHeight + 5) return el;
      el = el.parentElement;
    }
    // 兜底：按 class 关键字找（route-scroll-container / scroll-container / comment / list）
    el = list;
    while (el && el !== document.documentElement && el !== document.body) {
      const c = (el.className || "").toString();
      if (/scroll|comment|container|list/i.test(c) && el.scrollHeight > el.clientHeight + 5) return el;
      el = el.parentElement;
    }
    return null;
  };

  const fireScroll = (sc) => {
    // 多重触发，确保懒加载被唤醒
    if (sc) {
      try { sc.scrollTop = sc.scrollHeight; sc.scrollTop = sc.scrollHeight + 1200; sc.dispatchEvent(new Event("scroll")); } catch (e) {}
    }
    const list = q(SEL_LIST);
    if (list && list.scrollHeight > list.clientHeight + 5) {
      try { list.scrollTop = list.scrollHeight; list.dispatchEvent(new Event("scroll")); } catch (e) {}
    }
    try { window.scrollBy(0, 900); window.dispatchEvent(new Event("scroll")); } catch (e) {}
  };

  let sc = findScroller();
  const before = getCount();
  let last = before, stall = 0, rounds = 0;
  for (let i = 0; i < 45; i++) {
    sc = sc || findScroller();
    fireScroll(sc);
    await sleep(1000);
    rounds++;
    const n = getCount();
    if (n === last) { stall++; if (stall >= 5) break; } else { stall = 0; last = n; }
    if (n >= 120) break;
  }

  // 收尾：滚到顶再到底，把尾部评论带出
  if (sc) { try { sc.scrollTop = 0; } catch (e) {} await sleep(800); try { sc.scrollTop = sc.scrollHeight; } catch (e) {} await sleep(900); }

  // 3) 抽取评论条目（含作者标记 / 点赞 / 时间）
  const nodes = qa(SEL_LIST + " " + SEL_ITEM);
  const out = nodes.map(nd => (nd.innerText || "").split("\n").map(s => s.trim()).filter(Boolean));

  let desc = "", authorName = "", digg = "", commentCnt = "";
  try { const d = q(`[data-e2e="video-desc"]`); if (d) desc = (d.innerText || "").slice(0, 500); } catch (e) {}
  try { const a = q(`[data-e2e="video-author-nickname"]`); if (a) authorName = (a.innerText || "").trim(); } catch (e) {}
  try { const d = q(`[data-e2e="video-player-digg"]`); if (d) digg = (d.innerText || "").trim(); } catch (e) {}
  try { const c = q(`[data-e2e="video-comment-count"]`); if (c) commentCnt = (c.innerText || "").trim(); } catch (e) {}

  return {
    ok: true, url: url, n: out.length, comments: out, waited: waited, rounds: rounds,
    before: before, scFound: !!sc, desc: desc, authorName: authorName, digg: digg, commentCnt: commentCnt
  };
})()
